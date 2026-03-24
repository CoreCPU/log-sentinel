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


from log_sentinel.parsers.syslog_parser import SyslogParser


class TestSyslogParser:
    def setup_method(self):
        self.parser = SyslogParser()

    def test_rfc3164_format(self):
        line = "Mar 23 12:00:00 webserver sshd[1234]: Failed password for root from 10.0.0.1"
        entry = self.parser.parse(line, "/var/log/syslog")
        assert entry is not None
        assert entry.message == "Failed password for root from 10.0.0.1"
        assert entry.extra_fields["hostname"] == "webserver"
        assert entry.extra_fields["program"] == "sshd"
        assert entry.extra_fields["pid"] == "1234"

    def test_rfc3164_error_keyword(self):
        line = "Mar 23 12:00:00 db1 postgres[5678]: ERROR: relation does not exist"
        entry = self.parser.parse(line, "/var/log/syslog")
        assert entry is not None
        assert entry.severity == "error"

    def test_rfc3164_info_default(self):
        line = "Mar 23 12:00:00 web1 nginx[99]: started worker process"
        entry = self.parser.parse(line, "/var/log/syslog")
        assert entry is not None
        assert entry.severity == "info"

    def test_non_syslog_returns_none(self):
        entry = self.parser.parse('{"level": "info"}', "/var/log/syslog")
        assert entry is None


from log_sentinel.parsers.clf_parser import ClfParser


class TestClfParser:
    def setup_method(self):
        self.parser = ClfParser()

    def test_common_log_format(self):
        line = '10.0.0.1 - frank [23/Mar/2026:12:00:00 +0000] "GET /index.html HTTP/1.1" 200 1234'
        entry = self.parser.parse(line, "/var/log/nginx/access.log")
        assert entry is not None
        assert entry.severity == "info"
        assert "GET /index.html" in entry.message
        assert entry.extra_fields["status"] == 200
        assert entry.extra_fields["remote_host"] == "10.0.0.1"

    def test_5xx_is_error(self):
        line = '10.0.0.1 - - [23/Mar/2026:12:00:00 +0000] "POST /api HTTP/1.1" 500 0'
        entry = self.parser.parse(line, "/var/log/nginx/access.log")
        assert entry is not None
        assert entry.severity == "error"

    def test_4xx_is_warning(self):
        line = '10.0.0.1 - - [23/Mar/2026:12:00:00 +0000] "GET /missing HTTP/1.1" 404 0'
        entry = self.parser.parse(line, "/var/log/nginx/access.log")
        assert entry is not None
        assert entry.severity == "warning"

    def test_non_clf_returns_none(self):
        entry = self.parser.parse("just some random text", "/var/log/nginx/access.log")
        assert entry is None


from log_sentinel.parsers.fallback_parser import FallbackParser


class TestFallbackParser:
    def setup_method(self):
        self.parser = FallbackParser()

    def test_error_keyword(self):
        entry = self.parser.parse("2026-03-23 ERROR: connection refused", "/var/log/app.log")
        assert entry is not None
        assert entry.severity == "error"

    def test_fatal_keyword(self):
        entry = self.parser.parse("FATAL: out of memory", "/var/log/app.log")
        assert entry is not None
        assert entry.severity == "error"

    def test_warning_keyword(self):
        entry = self.parser.parse("WARN: disk usage at 90%", "/var/log/app.log")
        assert entry is not None
        assert entry.severity == "warning"

    def test_exception_keyword(self):
        entry = self.parser.parse("Exception in thread main", "/var/log/app.log")
        assert entry is not None
        assert entry.severity == "error"

    def test_traceback_keyword(self):
        entry = self.parser.parse("Traceback (most recent call last):", "/var/log/app.log")
        assert entry is not None
        assert entry.severity == "error"

    def test_no_keyword_is_info(self):
        entry = self.parser.parse("server started on port 8080", "/var/log/app.log")
        assert entry is not None
        assert entry.severity == "info"

    def test_always_returns_entry(self):
        entry = self.parser.parse("", "/var/log/app.log")
        assert entry is not None
