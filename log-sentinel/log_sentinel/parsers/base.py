from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class LogEntry:
    timestamp: datetime
    severity: str
    message: str
    source_file: str
    extra_fields: dict = field(default_factory=dict)


class BaseParser(ABC):
    @abstractmethod
    def parse(self, line: str, source_file: str) -> Optional[LogEntry]:
        """Attempt to parse a log line. Return LogEntry if successful, None if not."""
        ...
