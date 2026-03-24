import json
import logging
import os
import re
import tempfile
from typing import Optional

logger = logging.getLogger("log-sentinel")


class Tailer:
    def __init__(self, state_file: str):
        self._state_file = os.path.expanduser(state_file)
        self._positions: dict[str, dict] = {}
        self._corrupt_recovery = False
        self.skip_to_eof = False
        self._load_state()

    def _load_state(self):
        if os.path.exists(self._state_file):
            try:
                with open(self._state_file) as f:
                    self._positions = json.load(f)
            except (json.JSONDecodeError, OSError):
                logger.warning(
                    "Corrupt state file %s — resetting to EOF for all files", self._state_file
                )
                self._positions = {}
                self._corrupt_recovery = True

    def save_state(self):
        state_dir = os.path.dirname(self._state_file)
        if state_dir:
            os.makedirs(state_dir, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(dir=state_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._positions, f)
            os.rename(tmp_path, self._state_file)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def read_new_lines(
        self,
        path: str,
        multiline_pattern: Optional[str] = None,
    ) -> list[str]:
        try:
            stat = os.stat(path)
        except OSError:
            logger.warning("Cannot access %s — skipping", path)
            return []

        inode = stat.st_ino
        size = stat.st_size

        # On corrupt state recovery, skip to EOF for unknown files
        if self._corrupt_recovery and path not in self._positions:
            self._positions[path] = {"inode": inode, "offset": size}
            return []

        # Skip to EOF for first-time files when not in backfill mode
        if self.skip_to_eof and path not in self._positions:
            self._positions[path] = {"inode": inode, "offset": size}
            return []

        prev = self._positions.get(path, {})
        prev_inode = prev.get("inode")
        prev_offset = prev.get("offset", 0)
        prev_fingerprint = prev.get("fingerprint")

        # Detect rotation: inode change or file shrunk (truncation)
        rotated = prev_inode != inode or size < prev_offset

        # Fingerprint check: even if inode matches, verify file start hasn't changed
        # (Linux can reuse inodes on rapid delete+recreate)
        prev_fp_len = prev.get("fp_len", 0)
        if not rotated and prev_fingerprint is not None and prev_offset > 0 and prev_fp_len > 0:
            try:
                with open(path, "rb") as f:
                    head = f.read(prev_fp_len)
                if head.hex() != prev_fingerprint:
                    rotated = True
            except OSError:
                pass

        if rotated:
            prev_offset = 0

        if prev_offset >= size:
            return []

        fp_size = min(64, size)
        fingerprint = None
        try:
            with open(path, "rb") as fb:
                # Capture fingerprint on fresh reads (offset 0)
                if prev_offset == 0 and fp_size > 0:
                    fingerprint = fb.read(fp_size).hex()
                fb.seek(prev_offset)
                raw_bytes = fb.read()
                new_offset = fb.tell()
        except OSError:
            return []

        raw = raw_bytes.decode("utf-8", errors="replace")

        entry: dict = {"inode": inode, "offset": new_offset}
        if fingerprint is not None:
            entry["fingerprint"] = fingerprint
            entry["fp_len"] = fp_size
        elif prev_fingerprint is not None:
            entry["fingerprint"] = prev_fingerprint
            entry["fp_len"] = prev_fp_len
        self._positions[path] = entry

        raw_lines = raw.splitlines()
        if not raw_lines:
            return []

        if multiline_pattern:
            return self._aggregate_multiline(raw_lines, multiline_pattern)
        return raw_lines

    @staticmethod
    def _aggregate_multiline(raw_lines: list[str], pattern: str) -> list[str]:
        compiled = re.compile(pattern)
        aggregated: list[str] = []
        current: list[str] = []

        for line in raw_lines:
            if compiled.match(line):
                if current:
                    aggregated.append("\n".join(current))
                current = [line]
            else:
                if current:
                    current.append(line)
                else:
                    # Orphan continuation line — treat as standalone
                    current = [line]

        if current:
            aggregated.append("\n".join(current))

        return aggregated

    def remove_file(self, path: str):
        self._positions.pop(path, None)
