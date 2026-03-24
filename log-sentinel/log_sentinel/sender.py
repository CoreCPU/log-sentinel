import hashlib
import socket
import time
from collections import defaultdict

import sentry_sdk

from .parsers.base import LogEntry

SEVERITY_ORDER = {"debug": 0, "info": 1, "warning": 2, "error": 3}

_SENTRY_LEVEL_MAP = {
    "debug":   "debug",
    "info":    "info",
    "warning": "warning",
    "error":   "error",
}


class SentrySender:
    def __init__(self, dedup_window: int, breadcrumb_limit: int):
        self._dedup_window = dedup_window
        self._dedup_cache: dict[str, float] = {}
        self._dedup_counts: dict[str, int] = {}
        self._hostname = socket.gethostname()
        self.metrics = {
            "lines_processed": 0,
            "events_sent": 0,
            "parse_failures": 0,
        }

    def send(self, entry: LogEntry, min_severity: str, tags: dict, parser_name: str = "auto"):
        self.metrics["lines_processed"] += 1

        entry_level = SEVERITY_ORDER.get(entry.severity, 1)
        min_level = SEVERITY_ORDER.get(min_severity, 2)

        if entry_level < min_level:
            return

        fingerprint = self._fingerprint(entry)
        now = time.monotonic()
        self._expire_dedup(now)

        if fingerprint in self._dedup_cache:
            self._dedup_counts[fingerprint] = self._dedup_counts.get(fingerprint, 0) + 1
            return

        self._dedup_cache[fingerprint] = now
        suppressed_count = self._dedup_counts.pop(fingerprint, 0)

        # Build flat attributes dict — no new_scope(), no trace context interference
        attributes = {
            "log_source": entry.source_file,
            "log_parser": parser_name,
            "log_host": self._hostname,
        }
        for k, v in tags.items():
            attributes[k] = v
        if entry.extra_fields:
            for k, v in entry.extra_fields.items():
                attributes[k] = v
        if suppressed_count > 0:
            attributes["duplicate_count"] = suppressed_count

        level = _SENTRY_LEVEL_MAP.get(entry.severity, "error")
        log_fn = getattr(sentry_sdk.logger, level)
        log_fn(entry.message, **attributes)

        self.metrics["events_sent"] += 1

    def _fingerprint(self, entry: LogEntry) -> str:
        raw = f"{entry.severity}:{entry.source_file}:{entry.message}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _expire_dedup(self, now: float):
        expired = [k for k, t in self._dedup_cache.items() if now - t > self._dedup_window]
        for k in expired:
            del self._dedup_cache[k]
