import re
from datetime import datetime, timezone
from typing import Optional

from .base import BaseParser, LogEntry

ERROR_RE = re.compile(r"\b(ERROR|FATAL|CRIT(?:ICAL)?|ALERT|EMERG|Exception|Traceback)\b", re.IGNORECASE)
WARN_RE = re.compile(r"\b(WARN(?:ING)?)\b", re.IGNORECASE)


class FallbackParser(BaseParser):
    def parse(self, line: str, source_file: str) -> Optional[LogEntry]:
        if ERROR_RE.search(line):
            severity = "error"
        elif WARN_RE.search(line):
            severity = "warning"
        else:
            severity = "info"

        return LogEntry(
            timestamp=datetime.now(timezone.utc),
            severity=severity,
            message=line,
            source_file=source_file,
        )
