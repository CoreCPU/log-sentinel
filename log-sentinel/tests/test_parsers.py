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


from log_sentinel.parsers.json_parser import JsonParser


class TestJsonParser:
    def setup_method(self):
        self.parser = JsonParser()

    def test_valid_json_log(self):
        line = '{"level": "error", "message": "disk full", "timestamp": "2026-03-23T12:00:00Z", "host": "web1"}'
        entry = self.parser.parse(line, "/var/log/app.json")
        assert entry is not None
        assert entry.severity == "error"
        assert entry.message == "disk full"
        assert entry.extra_fields["host"] == "web1"
        assert entry.source_file == "/var/log/app.json"

    def test_json_with_alternate_level_keys(self):
        line = '{"severity": "warning", "msg": "slow query", "timestamp": "2026-03-23T12:00:00Z"}'
        entry = self.parser.parse(line, "/var/log/app.json")
        assert entry is not None
        assert entry.severity == "warning"
        assert entry.message == "slow query"

    def test_json_missing_message_uses_full_line(self):
        line = '{"level": "info", "timestamp": "2026-03-23T12:00:00Z"}'
        entry = self.parser.parse(line, "/var/log/app.json")
        assert entry is not None
        assert entry.message == line

    def test_non_json_returns_none(self):
        entry = self.parser.parse("not json at all", "/var/log/app.json")
        assert entry is None

    def test_json_without_timestamp_uses_now(self):
        line = '{"level": "error", "message": "oops"}'
        entry = self.parser.parse(line, "/var/log/app.json")
        assert entry is not None
        assert entry.timestamp is not None
