import hashlib
import logging
import socket
import time
from collections import defaultdict, deque

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from .parsers.base import LogEntry

SEVERITY_ORDER = {"debug": 0, "info": 1, "warning": 2, "error": 3}

# Map our severity names to Python logging levels (used by sentry_sdk.logger)
_PY_LEVELS = {
    "debug":   logging.DEBUG,
    "info":    logging.INFO,
    "warning": logging.WARNING,
    "error":   logging.ERROR,
}

# sentry_sdk.logger methods by severity
_SENTRY_LOG_FN = {
    "debug":   sentry_sdk.logger.debug,
    "info":    sentry_sdk.logger.info,
    "warning": sentry_sdk.logger.warning,
    "error":   sentry_sdk.logger.error,
}


class SentrySender:
    def __init__(self, dedup_window: int, breadcrumb_limit: int):
        self._dedup_window = dedup_window
        self._breadcrumb_limit = breadcrumb_limit  # kept for compat, unused with logs API
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

        # Dedup check (still useful to avoid log spam)
        fingerprint = self._fingerprint(entry)
        now = time.monotonic()
        self._expire_dedup(now)

        if fingerprint in self._dedup_cache:
            self._dedup_counts[fingerprint] = self._dedup_counts.get(fingerprint, 0) + 1
            return

        self._dedup_cache[fingerprint] = now
        suppressed_count = self._dedup_counts.pop(fingerprint, 0)

        # Build structured attributes for Sentry Logs
        attributes = {
            "log.source": entry.source_file,
            "log.parser": parser_name,
            "log.host": self._hostname,
            **tags,
        }
        if entry.extra_fields:
            attributes.update({f"http.{k}": v for k, v in entry.extra_fields.items()})
        if suppressed_count > 0:
            attributes["duplicate_count"] = suppressed_count

        log_fn = _SENTRY_LOG_FN.get(entry.severity, sentry_sdk.logger.error)

        with sentry_sdk.new_scope() as scope:
            scope.set_extra("_log_attributes", attributes)
            log_fn(entry.message, **{k: v for k, v in attributes.items()
                                     if isinstance(v, (str, int, float, bool))})

        self.metrics["events_sent"] += 1

    def _fingerprint(self, entry: LogEntry) -> str:
        raw = f"{entry.severity}:{entry.source_file}:{entry.message}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _expire_dedup(self, now: float):
        expired = [k for k, t in self._dedup_cache.items() if now - t > self._dedup_window]
        for k in expired:
            del self._dedup_cache[k]
