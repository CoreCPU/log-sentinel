import re
from datetime import datetime, timezone
from typing import Optional

from .base import BaseParser, LogEntry

RFC3164_RE = re.compile(
    r"^(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<hostname>\S+)\s+"
    r"(?P<program>[^\[:\s]+)"
    r"(?:\[(?P<pid>\d+)\])?:\s+"
    r"(?P<message>.+)$"
)

ERROR_KEYWORDS = re.compile(r"\b(ERROR|FATAL|CRIT|ALERT|EMERG)\b", re.IGNORECASE)
WARN_KEYWORDS = re.compile(r"\b(WARN|WARNING)\b", re.IGNORECASE)


class SyslogParser(BaseParser):
    def parse(self, line: str, source_file: str) -> Optional[LogEntry]:
        match = RFC3164_RE.match(line)
        if not match:
            return None

        groups = match.groupdict()
        message = groups["message"]

        if ERROR_KEYWORDS.search(message):
            severity = "error"
        elif WARN_KEYWORDS.search(message):
            severity = "warning"
        else:
            severity = "info"

        timestamp = self._parse_timestamp(groups["timestamp"])

        extra = {"hostname": groups["hostname"], "program": groups["program"]}
        if groups.get("pid"):
            extra["pid"] = groups["pid"]

        return LogEntry(
            timestamp=timestamp,
            severity=severity,
            message=message,
            source_file=source_file,
            extra_fields=extra,
        )

    @staticmethod
    def _parse_timestamp(raw: str) -> datetime:
        now = datetime.now(timezone.utc)
        try:
            dt = datetime.strptime(raw, "%b %d %H:%M:%S")
            dt = dt.replace(year=now.year, tzinfo=timezone.utc)
            return dt
        except ValueError:
            return now
