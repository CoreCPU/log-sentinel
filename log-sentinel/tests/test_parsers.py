from datetime import datetime, timezone
from log_sentinel.parsers.base import LogEntry, BaseParser


def test_log_entry_creation():
    entry = LogEntry(
        timestamp=datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone.utc),
        severity="error",
        message="something broke",
        source_file="/var/log/app.log",
        extra_fields={"request_id": "abc123"},
    )
    assert entry.severity == "error"
    assert entry.message == "something broke"
    assert entry.extra_fields["request_id"] == "abc123"


def test_log_entry_defaults():
    entry = LogEntry(
        timestamp=datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone.utc),
        severity="info",
        message="hello",
        source_file="/var/log/app.log",
    )
    assert entry.extra_fields == {}


def test_base_parser_is_abstract():
    import pytest
    with pytest.raises(TypeError):
        BaseParser()
