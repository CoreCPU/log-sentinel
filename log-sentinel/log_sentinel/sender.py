import hashlib
import socket
import time
from collections import defaultdict, deque

import sentry_sdk

from .parsers.base import LogEntry

SEVERITY_ORDER = {"debug": 0, "info": 1, "warning": 2, "error": 3}
SENTRY_LEVELS = {"error": "error", "warning": "warning", "info": "info", "debug": "debug"}


class SentrySender:
    def __init__(self, dedup_window: int, breadcrumb_limit: int):
        self._dedup_window = dedup_window
        self._breadcrumb_limit = breadcrumb_limit
        self._dedup_cache: dict[str, float] = {}
        self._dedup_counts: dict[str, int] = {}
        self._breadcrumbs: dict[str, deque] = defaultdict(deque)
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

        # Info/debug -> breadcrumb, not an event
        if entry.severity in ("info", "debug"):
            self._add_breadcrumb(entry)
            return

        # Dedup check
        fingerprint = self._fingerprint(entry)
        now = time.monotonic()
        self._expire_dedup(now)

        if fingerprint in self._dedup_cache:
            self._dedup_counts[fingerprint] = self._dedup_counts.get(fingerprint, 0) + 1
            return

        self._dedup_cache[fingerprint] = now
        suppressed_count = self._dedup_counts.pop(fingerprint, 0)

        # Flush breadcrumbs for this source before sending event
        self._flush_breadcrumbs(entry.source_file)

        all_tags = {
            "log.source": entry.source_file,
            "log.parser": parser_name,
            "log.host": self._hostname,
            **tags,
        }

        with sentry_sdk.new_scope() as scope:
            for k, v in all_tags.items():
                scope.set_tag(k, v)
            context = dict(entry.extra_fields) if entry.extra_fields else {}
            if suppressed_count > 0:
                context["duplicate_count"] = suppressed_count
            if context:
                scope.set_context("log_entry", context)

            sentry_sdk.capture_message(
                entry.message,
                level=SENTRY_LEVELS.get(entry.severity, "error"),
            )

        self.metrics["events_sent"] += 1

    def _fingerprint(self, entry: LogEntry) -> str:
        raw = f"{entry.severity}:{entry.source_file}:{entry.message}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _expire_dedup(self, now: float):
        expired = [k for k, t in self._dedup_cache.items() if now - t > self._dedup_window]
        for k in expired:
            del self._dedup_cache[k]

    def _add_breadcrumb(self, entry: LogEntry):
        bc = {
            "message": entry.message,
            "level": entry.severity,
            "timestamp": entry.timestamp.isoformat(),
            "data": entry.extra_fields,
        }
        buf = self._breadcrumbs[entry.source_file]
        buf.append(bc)
        while len(buf) > self._breadcrumb_limit:
            buf.popleft()

    def _flush_breadcrumbs(self, source_file: str):
        buf = self._breadcrumbs.get(source_file)
        if not buf:
            return
        for bc in buf:
            sentry_sdk.add_breadcrumb(
                message=bc["message"],
                level=bc["level"],
                timestamp=bc["timestamp"],
                data=bc.get("data"),
            )
        buf.clear()
