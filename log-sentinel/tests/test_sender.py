import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from log_sentinel.parsers.base import LogEntry
from log_sentinel.sender import SentrySender


def make_entry(severity="error", message="test error", source="/app.log"):
    return LogEntry(
        timestamp=datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone.utc),
        severity=severity,
        message=message,
        source_file=source,
    )


class TestSeverityFiltering:
    def test_filters_below_threshold(self):
        sender = SentrySender(dedup_window=60, breadcrumb_limit=100)
        with patch("sentry_sdk.capture_message") as mock_capture:
            sender.send(make_entry(severity="info"), min_severity="warning", tags={})
            mock_capture.assert_not_called()

    def test_passes_at_threshold(self):
        sender = SentrySender(dedup_window=60, breadcrumb_limit=100)
        with patch("sentry_sdk.capture_message") as mock_capture:
            sender.send(make_entry(severity="warning"), min_severity="warning", tags={})
            mock_capture.assert_called_once()

    def test_passes_above_threshold(self):
        sender = SentrySender(dedup_window=60, breadcrumb_limit=100)
        with patch("sentry_sdk.capture_message") as mock_capture:
            sender.send(make_entry(severity="error"), min_severity="info", tags={})
            mock_capture.assert_called_once()


class TestDeduplication:
    def test_duplicate_suppressed(self):
        sender = SentrySender(dedup_window=60, breadcrumb_limit=100)
        with patch("sentry_sdk.capture_message") as mock_capture:
            sender.send(make_entry(), min_severity="error", tags={})
            sender.send(make_entry(), min_severity="error", tags={})
            assert mock_capture.call_count == 1

    def test_different_messages_not_suppressed(self):
        sender = SentrySender(dedup_window=60, breadcrumb_limit=100)
        with patch("sentry_sdk.capture_message") as mock_capture:
            sender.send(make_entry(message="error 1"), min_severity="error", tags={})
            sender.send(make_entry(message="error 2"), min_severity="error", tags={})
            assert mock_capture.call_count == 2

    def test_dedup_expires_after_window(self):
        sender = SentrySender(dedup_window=1, breadcrumb_limit=100)
        with patch("sentry_sdk.capture_message") as mock_capture, \
             patch("time.monotonic") as mock_time:
            mock_time.return_value = 100.0
            sender.send(make_entry(), min_severity="error", tags={})
            # Same message after window expires
            mock_time.return_value = 161.1
            sender.send(make_entry(), min_severity="error", tags={})
            assert mock_capture.call_count == 2


class TestBreadcrumbs:
    def test_info_accumulated_as_breadcrumb(self):
        sender = SentrySender(dedup_window=60, breadcrumb_limit=100)
        with patch("sentry_sdk.capture_message") as mock_capture:
            sender.send(make_entry(severity="info", source="/app.log"), min_severity="info", tags={})
            mock_capture.assert_not_called()
            assert len(sender._breadcrumbs["/app.log"]) == 1

    def test_breadcrumbs_attached_to_error(self):
        sender = SentrySender(dedup_window=60, breadcrumb_limit=100)
        with patch("sentry_sdk.capture_message") as mock_capture, \
             patch("sentry_sdk.add_breadcrumb") as mock_breadcrumb:
            sender.send(make_entry(severity="info", message="context", source="/app.log"), min_severity="info", tags={})
            sender.send(make_entry(severity="error", message="boom", source="/app.log"), min_severity="info", tags={})
            mock_breadcrumb.assert_called_once()
            mock_capture.assert_called_once()

    def test_breadcrumbs_bounded(self):
        sender = SentrySender(dedup_window=60, breadcrumb_limit=3)
        with patch("sentry_sdk.capture_message"):
            for i in range(5):
                sender.send(
                    make_entry(severity="info", message=f"msg {i}", source="/app.log"),
                    min_severity="info",
                    tags={},
                )
            assert len(sender._breadcrumbs["/app.log"]) == 3
            # Should have the last 3
            messages = [b["message"] for b in sender._breadcrumbs["/app.log"]]
            assert messages == ["msg 2", "msg 3", "msg 4"]


class TestMetrics:
    def test_events_sent_counter(self):
        sender = SentrySender(dedup_window=60, breadcrumb_limit=100)
        with patch("sentry_sdk.capture_message"):
            sender.send(make_entry(), min_severity="error", tags={})
            assert sender.metrics["events_sent"] == 1

    def test_lines_processed_counter(self):
        sender = SentrySender(dedup_window=60, breadcrumb_limit=100)
        with patch("sentry_sdk.capture_message"):
            sender.send(make_entry(), min_severity="error", tags={})
            sender.send(make_entry(severity="info"), min_severity="info", tags={})
            assert sender.metrics["lines_processed"] == 2
