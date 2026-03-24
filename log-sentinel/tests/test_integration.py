import json
import os
import tempfile
import urllib.request
import urllib.error

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from log_sentinel.config import load_config
from log_sentinel.tailer import Tailer
from log_sentinel.sender import SentrySender
from log_sentinel.parsers import parse_line
from log_sentinel.health import HealthServer


class CaptureTransport(Transport):
    """Sentry transport that captures events in memory instead of sending."""

    def __init__(self, options=None):
        self.events = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.headers.get("type") == "event":
                self.events.append(json.loads(item.payload.get_bytes()))


class TestEndToEnd:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmpdir, "state.json")
        self.log_file = os.path.join(self.tmpdir, "test.log")

        # Create empty log file
        with open(self.log_file, "w") as f:
            pass

        self.transport = CaptureTransport()
        sentry_sdk.init(
            dsn="https://examplePublicKey@o0.ingest.sentry.io/0",
            transport=self.transport,
        )

    def test_error_line_creates_sentry_event(self):
        tailer = Tailer(self.state_file)
        sender = SentrySender(dedup_window=60, breadcrumb_limit=100)

        with open(self.log_file, "a") as f:
            f.write('{"level": "error", "message": "database connection lost", "timestamp": "2026-03-23T12:00:00Z"}\n')

        lines = tailer.read_new_lines(self.log_file)
        assert len(lines) == 1

        entry = parse_line(lines[0], self.log_file, parser_hint="json")
        assert entry is not None
        assert entry.severity == "error"

        sender.send(entry, min_severity="warning", tags={"env": "test"})
        sentry_sdk.flush()

        assert sender.metrics["events_sent"] == 1

    def test_info_not_sent_with_warning_threshold(self):
        tailer = Tailer(self.state_file)
        sender = SentrySender(dedup_window=60, breadcrumb_limit=100)

        with open(self.log_file, "a") as f:
            f.write('{"level": "info", "message": "all good"}\n')

        lines = tailer.read_new_lines(self.log_file)
        entry = parse_line(lines[0], self.log_file)
        sender.send(entry, min_severity="warning", tags={})
        sentry_sdk.flush()

        assert sender.metrics["events_sent"] == 0

    def test_multiline_stack_trace(self):
        tailer = Tailer(self.state_file)

        with open(self.log_file, "a") as f:
            f.write("2026-03-23 ERROR: something failed\n")
            f.write("  at module.function(file.py:10)\n")
            f.write("  at main(file.py:50)\n")
            f.write("2026-03-23 INFO: next entry\n")

        lines = tailer.read_new_lines(self.log_file, multiline_pattern=r"^\d{4}-\d{2}-\d{2}")
        assert len(lines) == 2
        assert "at module.function" in lines[0]

    def test_syslog_format(self):
        tailer = Tailer(self.state_file)
        sender = SentrySender(dedup_window=60, breadcrumb_limit=100)

        with open(self.log_file, "a") as f:
            f.write("Mar 23 12:00:00 webserver sshd[1234]: ERROR: authentication failure\n")

        lines = tailer.read_new_lines(self.log_file)
        entry = parse_line(lines[0], self.log_file)
        assert entry.severity == "error"

        sender.send(entry, min_severity="warning", tags={})
        assert sender.metrics["events_sent"] == 1

    def test_clf_format(self):
        tailer = Tailer(self.state_file)
        sender = SentrySender(dedup_window=60, breadcrumb_limit=100)

        with open(self.log_file, "a") as f:
            f.write('10.0.0.1 - - [23/Mar/2026:12:00:00 +0000] "GET /api HTTP/1.1" 503 0\n')

        lines = tailer.read_new_lines(self.log_file)
        entry = parse_line(lines[0], self.log_file, parser_hint="clf")
        assert entry.severity == "error"

        sender.send(entry, min_severity="warning", tags={})
        assert sender.metrics["events_sent"] == 1


class TestHealthEndpoint:
    def test_health_returns_metrics(self):
        metrics = {"lines_processed": 42, "events_sent": 5, "parse_failures": 1}
        server = HealthServer(port=18099, metrics_fn=lambda: metrics)
        server.start()
        try:
            resp = urllib.request.urlopen("http://127.0.0.1:18099/health")
            data = json.loads(resp.read())
            assert data["status"] == "ok"
            assert data["lines_processed"] == 42
            assert data["events_sent"] == 5
        finally:
            server.stop()

    def test_health_404_on_other_paths(self):
        metrics = {}
        server = HealthServer(port=18098, metrics_fn=lambda: metrics)
        server.start()
        try:
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen("http://127.0.0.1:18098/other")
            assert exc_info.value.code == 404
        finally:
            server.stop()
