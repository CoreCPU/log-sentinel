import json
from datetime import datetime, timezone
from typing import Optional

from .base import BaseParser, LogEntry

LEVEL_KEYS = ("level", "severity", "loglevel", "log_level")
MESSAGE_KEYS = ("message", "msg", "text", "body")
TIMESTAMP_KEYS = ("timestamp", "time", "ts", "datetime", "@timestamp")

LEVEL_MAP = {
    "fatal": "error",
    "critical": "error",
    "err": "error",
    "error": "error",
    "warn": "warning",
    "warning": "warning",
    "info": "info",
    "debug": "debug",
    "trace": "debug",
}


class JsonParser(BaseParser):
    def parse(self, line: str, source_file: str) -> Optional[LogEntry]:
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(data, dict):
            return None

        severity = self._extract(data, LEVEL_KEYS)
        severity = LEVEL_MAP.get(severity.lower(), "info") if severity else "info"

        message = self._extract(data, MESSAGE_KEYS) or line

        ts_raw = self._extract(data, TIMESTAMP_KEYS)
        timestamp = self._parse_timestamp(ts_raw)

        extra = {k: v for k, v in data.items()
                 if k not in {*LEVEL_KEYS, *MESSAGE_KEYS, *TIMESTAMP_KEYS}}

        return LogEntry(
            timestamp=timestamp,
            severity=severity,
            message=message,
            source_file=source_file,
            extra_fields=extra,
        )

    @staticmethod
    def _extract(data: dict, keys: tuple) -> Optional[str]:
        for key in keys:
            if key in data:
                return str(data[key])
        return None

    @staticmethod
    def _parse_timestamp(raw: Optional[str]) -> datetime:
        if not raw:
            return datetime.now(timezone.utc)
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(raw, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        return datetime.now(timezone.utc)
