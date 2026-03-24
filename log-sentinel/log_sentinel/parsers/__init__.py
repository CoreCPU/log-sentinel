from typing import Optional

from .base import BaseParser, LogEntry
from .json_parser import JsonParser
from .syslog_parser import SyslogParser
from .clf_parser import ClfParser
from .fallback_parser import FallbackParser

PARSER_REGISTRY = {
    "json": JsonParser,
    "syslog": SyslogParser,
    "clf": ClfParser,
    "fallback": FallbackParser,
}

DEFAULT_CHAIN_ORDER = ["json", "syslog", "clf", "fallback"]


def build_parser_chain(parser_hint: Optional[str] = None) -> list[BaseParser]:
    if parser_hint and parser_hint in PARSER_REGISTRY:
        return [PARSER_REGISTRY[parser_hint](), FallbackParser()]
    return [PARSER_REGISTRY[name]() for name in DEFAULT_CHAIN_ORDER]


def parse_line(
    line: str,
    source_file: str,
    parser_hint: Optional[str] = None,
) -> Optional[LogEntry]:
    chain = build_parser_chain(parser_hint)
    for parser in chain:
        entry = parser.parse(line, source_file)
        if entry is not None:
            return entry
    return None
