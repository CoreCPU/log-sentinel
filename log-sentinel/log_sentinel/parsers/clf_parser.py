import re
from datetime import datetime, timezone
from typing import Optional

from .base import BaseParser, LogEntry

CLF_RE = re.compile(
    r'^(?P<remote>\S+)\s+'
    r'\S+\s+'
    r'(?P<user>\S+)\s+'
    r'\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<request>[^"]*)"\s+'
    r'(?P<status>\d{3})\s+'
    r'(?P<size>\S+)'
)


class ClfParser(BaseParser):
    def parse(self, line: str, source_file: str) -> Optional[LogEntry]:
        match = CLF_RE.match(line)
        if not match:
            return None

        groups = match.groupdict()
        status = int(groups["status"])

        if status >= 500:
            severity = "error"
        elif status >= 400:
            severity = "warning"
        else:
            severity = "info"

        timestamp = self._parse_timestamp(groups["time"])

        size_raw = groups["size"]
        size = int(size_raw) if size_raw != "-" else 0

        return LogEntry(
            timestamp=timestamp,
            severity=severity,
            message=groups["request"],
            source_file=source_file,
            extra_fields={
                "remote_host": groups["remote"],
                "user": groups["user"],
                "status": status,
                "size": size,
            },
        )

    @staticmethod
    def _parse_timestamp(raw: str) -> datetime:
        try:
            return datetime.strptime(raw, "%d/%b/%Y:%H:%M:%S %z")
        except ValueError:
            return datetime.now(timezone.utc)
