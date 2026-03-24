# Log Sentinel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python daemon that watches log files in real-time and forwards events to Sentry.io for error detection, observability, and incident correlation.

**Architecture:** A pipeline of Watcher → Tailer → Parsers → Sender. The watcher monitors filesystem events via `watchdog`, the tailer manages file positions and multi-line aggregation, parsers normalize log lines into `LogEntry` dataclasses via chain-of-responsibility, and the sender forwards to Sentry with severity filtering, deduplication, and breadcrumb management.

**Tech Stack:** Python 3.10+, watchdog, sentry-sdk, pyyaml, pytest

**Spec:** `docs/superpowers/specs/2026-03-23-log-sentinel-design.md`

---

## File Structure

All paths relative to `/opt/logs/log-sentinel/`:

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Package metadata, dependencies, entry point |
| `config.yaml` | Example configuration |
| `log_sentinel/__init__.py` | Package init, version |
| `log_sentinel/__main__.py` | Entry point: arg parsing, config load, daemon loop, signal handling |
| `log_sentinel/config.py` | Config loading, validation, dataclasses for typed config |
| `log_sentinel/watcher.py` | Filesystem monitoring via watchdog, glob re-expansion |
| `log_sentinel/tailer.py` | File position tracking, rotation detection, multi-line aggregation, atomic state persistence |
| `log_sentinel/sender.py` | Sentry SDK interaction, severity filtering, dedup, breadcrumbs |
| `log_sentinel/health.py` | HTTP health check endpoint |
| `log_sentinel/parsers/__init__.py` | Parser chain assembly |
| `log_sentinel/parsers/base.py` | `LogEntry` dataclass, `BaseParser` ABC |
| `log_sentinel/parsers/json_parser.py` | JSON log line parser |
| `log_sentinel/parsers/syslog_parser.py` | RFC 3164 syslog parser (RFC 5424 deferred) |
| `log_sentinel/parsers/clf_parser.py` | Common/Combined Log Format parser |
| `log_sentinel/parsers/fallback_parser.py` | Keyword-based severity detection |
| `tests/test_config.py` | Config loading and validation tests |
| `tests/test_parsers.py` | All parser unit tests |
| `tests/test_tailer.py` | Tailer unit tests (positions, rotation, multi-line) |
| `tests/test_sender.py` | Sender unit tests (filtering, dedup, breadcrumbs) |
| `tests/test_integration.py` | End-to-end: write to file → assert Sentry events |
| `log-sentinel.service` | systemd unit file |
| `requirements.txt` | Pinned dependencies |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `log-sentinel/pyproject.toml`
- Create: `log-sentinel/requirements.txt`
- Create: `log-sentinel/log_sentinel/__init__.py`
- Create: `log-sentinel/log_sentinel/parsers/__init__.py`
- Create: `log-sentinel/tests/__init__.py`

- [ ] **Step 1: Create project directory structure**

```bash
mkdir -p /opt/logs/log-sentinel/log_sentinel/parsers
mkdir -p /opt/logs/log-sentinel/tests
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "log-sentinel"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "watchdog>=3.0",
    "sentry-sdk>=1.40",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Create `requirements.txt`**

```
watchdog>=3.0
sentry-sdk>=1.40
pyyaml>=6.0
pytest>=7.0
```

- [ ] **Step 4: Create `log_sentinel/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 5: Create empty `__init__.py` files**

Create empty `log_sentinel/parsers/__init__.py` and `tests/__init__.py`.

- [ ] **Step 6: Install dependencies**

```bash
cd /opt/logs/log-sentinel
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

- [ ] **Step 7: Verify pytest runs**

```bash
cd /opt/logs/log-sentinel
source venv/bin/activate
pytest --co
```

Expected: no errors, 0 tests collected.

- [ ] **Step 8: Commit**

```bash
git add log-sentinel/
git commit -m "feat: scaffold log-sentinel project with dependencies"
```

---

## Task 2: LogEntry Dataclass and BaseParser ABC

**Files:**
- Create: `log-sentinel/log_sentinel/parsers/base.py`
- Create: `log-sentinel/tests/test_parsers.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_parsers.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_parsers.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: Write implementation**

In `log_sentinel/parsers/base.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_parsers.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add log-sentinel/log_sentinel/parsers/base.py log-sentinel/tests/test_parsers.py
git commit -m "feat: add LogEntry dataclass and BaseParser ABC"
```

---

## Task 3: JSON Parser

**Files:**
- Create: `log-sentinel/log_sentinel/parsers/json_parser.py`
- Modify: `log-sentinel/tests/test_parsers.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_parsers.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_parsers.py::TestJsonParser -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: Write implementation**

In `log_sentinel/parsers/json_parser.py`:

```python
import json
from datetime import datetime, timezone
from typing import Optional

from .base import BaseParser, LogEntry

LEVEL_KEYS = ("level", "severity", "loglevel", "log_level")
MESSAGE_KEYS = ("message", "msg", "text", "body")
TIMESTAMP_KEYS = ("timestamp", "time", "ts", "datetime", "@timestamp")

LEVEL_MAP = {
    "fatal": "error",
    "critical": "error",
    "err": "error",
    "error": "error",
    "warn": "warning",
    "warning": "warning",
    "info": "info",
    "debug": "debug",
    "trace": "debug",
}


class JsonParser(BaseParser):
    def parse(self, line: str, source_file: str) -> Optional[LogEntry]:
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(data, dict):
            return None

        severity = self._extract(data, LEVEL_KEYS)
        severity = LEVEL_MAP.get(severity.lower(), "info") if severity else "info"

        message = self._extract(data, MESSAGE_KEYS) or line

        ts_raw = self._extract(data, TIMESTAMP_KEYS)
        timestamp = self._parse_timestamp(ts_raw)

        extra = {k: v for k, v in data.items()
                 if k not in {*LEVEL_KEYS, *MESSAGE_KEYS, *TIMESTAMP_KEYS}}

        return LogEntry(
            timestamp=timestamp,
            severity=severity,
            message=message,
            source_file=source_file,
            extra_fields=extra,
        )

    @staticmethod
    def _extract(data: dict, keys: tuple) -> Optional[str]:
        for key in keys:
            if key in data:
                return str(data[key])
        return None

    @staticmethod
    def _parse_timestamp(raw: Optional[str]) -> datetime:
        if not raw:
            return datetime.now(timezone.utc)
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(raw, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        return datetime.now(timezone.utc)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_parsers.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add log-sentinel/log_sentinel/parsers/json_parser.py log-sentinel/tests/test_parsers.py
git commit -m "feat: add JSON log parser"
```

---

## Task 4: Syslog Parser

**Files:**
- Create: `log-sentinel/log_sentinel/parsers/syslog_parser.py`
- Modify: `log-sentinel/tests/test_parsers.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_parsers.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_parsers.py::TestSyslogParser -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: Write implementation**

In `log_sentinel/parsers/syslog_parser.py`:

```python
import re
from datetime import datetime, timezone
from typing import Optional

from .base import BaseParser, LogEntry

# RFC 3164: "Mon DD HH:MM:SS hostname program[pid]: message"
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_parsers.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add log-sentinel/log_sentinel/parsers/syslog_parser.py log-sentinel/tests/test_parsers.py
git commit -m "feat: add syslog parser (RFC 3164)"
```

---

## Task 5: CLF Parser (Common/Combined Log Format)

**Files:**
- Create: `log-sentinel/log_sentinel/parsers/clf_parser.py`
- Modify: `log-sentinel/tests/test_parsers.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_parsers.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_parsers.py::TestClfParser -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: Write implementation**

In `log_sentinel/parsers/clf_parser.py`:

```python
import re
from datetime import datetime, timezone
from typing import Optional

from .base import BaseParser, LogEntry

# Common Log Format (also matches Combined with trailing fields)
CLF_RE = re.compile(
    r'^(?P<remote>\S+)\s+'       # remote host
    r'\S+\s+'                     # ident (always -)
    r'(?P<user>\S+)\s+'          # remote user
    r'\[(?P<time>[^\]]+)\]\s+'   # timestamp
    r'"(?P<request>[^"]*)"\s+'   # request line
    r'(?P<status>\d{3})\s+'      # status code
    r'(?P<size>\S+)'             # response size
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_parsers.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add log-sentinel/log_sentinel/parsers/clf_parser.py log-sentinel/tests/test_parsers.py
git commit -m "feat: add CLF parser (Common/Combined Log Format)"
```

---

## Task 6: Fallback Parser

**Files:**
- Create: `log-sentinel/log_sentinel/parsers/fallback_parser.py`
- Modify: `log-sentinel/tests/test_parsers.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_parsers.py`:

```python
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
        """Fallback parser never returns None — it's the last resort."""
        entry = self.parser.parse("", "/var/log/app.log")
        assert entry is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_parsers.py::TestFallbackParser -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: Write implementation**

In `log_sentinel/parsers/fallback_parser.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_parsers.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add log-sentinel/log_sentinel/parsers/fallback_parser.py log-sentinel/tests/test_parsers.py
git commit -m "feat: add fallback parser with keyword-based severity"
```

---

## Task 7: Parser Chain Assembly

**Files:**
- Modify: `log-sentinel/log_sentinel/parsers/__init__.py`
- Modify: `log-sentinel/tests/test_parsers.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_parsers.py`:

```python
from log_sentinel.parsers import build_parser_chain, parse_line


class TestParserChain:
    def test_json_detected_first(self):
        entry = parse_line('{"level": "error", "message": "boom"}', "/app.log")
        assert entry is not None
        assert entry.severity == "error"
        assert entry.message == "boom"

    def test_syslog_detected(self):
        entry = parse_line(
            "Mar 23 12:00:00 web1 nginx[99]: started",
            "/var/log/syslog",
        )
        assert entry is not None
        assert entry.extra_fields.get("program") == "nginx"

    def test_clf_detected(self):
        entry = parse_line(
            '10.0.0.1 - - [23/Mar/2026:12:00:00 +0000] "GET / HTTP/1.1" 200 0',
            "/var/log/access.log",
        )
        assert entry is not None
        assert entry.extra_fields.get("status") == 200

    def test_fallback_catches_all(self):
        entry = parse_line("some random log text", "/var/log/app.log")
        assert entry is not None
        assert entry.severity == "info"

    def test_parser_hint_skips_chain(self):
        chain = build_parser_chain(parser_hint="clf")
        # This is JSON but we forced CLF parser — should fall through to fallback
        entry = None
        for parser in chain:
            entry = parser.parse('{"level":"error"}', "/app.log")
            if entry is not None:
                break
        # CLF won't match JSON, fallback will catch it
        assert entry is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_parsers.py::TestParserChain -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: Write implementation**

In `log_sentinel/parsers/__init__.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_parsers.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add log-sentinel/log_sentinel/parsers/__init__.py log-sentinel/tests/test_parsers.py
git commit -m "feat: assemble parser chain with hint support"
```

---

## Task 8: Configuration Loading and Validation

**Files:**
- Create: `log-sentinel/log_sentinel/config.py`
- Create: `log-sentinel/tests/test_config.py`
- Create: `log-sentinel/config.yaml`

- [ ] **Step 1: Write failing tests**

In `tests/test_config.py`:

```python
import os
import pytest
import tempfile
import yaml
from log_sentinel.config import load_config, ConfigError, SentinelConfig


class TestConfigLoading:
    def _write_config(self, data: dict) -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        yaml.dump(data, f)
        f.close()
        return f.name

    def test_minimal_valid_config(self):
        path = self._write_config({
            "sentry_dsn": "https://key@sentry.io/123",
            "targets": [{"path": "/var/log/syslog"}],
        })
        config = load_config(path)
        assert config.sentry_dsn == "https://key@sentry.io/123"
        assert len(config.targets) == 1
        assert config.targets[0].min_severity == "warning"  # default
        os.unlink(path)

    def test_dsn_from_env(self, monkeypatch):
        monkeypatch.setenv("SENTRY_DSN", "https://env@sentry.io/456")
        path = self._write_config({
            "targets": [{"path": "/var/log/syslog"}],
        })
        config = load_config(path)
        assert config.sentry_dsn == "https://env@sentry.io/456"
        os.unlink(path)

    def test_missing_dsn_raises(self, monkeypatch):
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        path = self._write_config({
            "targets": [{"path": "/var/log/syslog"}],
        })
        with pytest.raises(ConfigError, match="sentry_dsn"):
            load_config(path)
        os.unlink(path)

    def test_defaults_section_inherited(self):
        path = self._write_config({
            "sentry_dsn": "https://key@sentry.io/123",
            "defaults": {"min_severity": "error", "polling": True},
            "targets": [{"path": "/var/log/syslog"}],
        })
        config = load_config(path)
        assert config.targets[0].min_severity == "error"
        assert config.targets[0].polling is True
        os.unlink(path)

    def test_missing_targets_raises(self):
        path = self._write_config({
            "sentry_dsn": "https://key@sentry.io/123",
        })
        with pytest.raises(ConfigError, match="target"):
            load_config(path)
        os.unlink(path)

    def test_target_without_path_raises(self):
        path = self._write_config({
            "sentry_dsn": "https://key@sentry.io/123",
            "targets": [{"parser": "json"}],
        })
        with pytest.raises(ConfigError, match="path"):
            load_config(path)
        os.unlink(path)

    def test_per_target_overrides(self):
        path = self._write_config({
            "sentry_dsn": "https://key@sentry.io/123",
            "targets": [{
                "path": "/var/log/app.log",
                "parser": "json",
                "min_severity": "error",
                "tags": {"env": "prod"},
            }],
        })
        config = load_config(path)
        t = config.targets[0]
        assert t.parser == "json"
        assert t.min_severity == "error"
        assert t.tags == {"env": "prod"}
        os.unlink(path)

    def test_global_defaults(self):
        path = self._write_config({
            "sentry_dsn": "https://key@sentry.io/123",
            "targets": [{"path": "/var/log/syslog"}],
            "dedup_window": 120,
            "breadcrumb_limit": 50,
            "glob_rescan_interval": 10,
            "health_check_port": 0,
        })
        config = load_config(path)
        assert config.dedup_window == 120
        assert config.breadcrumb_limit == 50
        assert config.glob_rescan_interval == 10
        assert config.health_check_port == 0
        os.unlink(path)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: Write implementation**

In `log_sentinel/config.py`:

```python
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


class ConfigError(Exception):
    pass


SEVERITY_LEVELS = ("debug", "info", "warning", "error")


@dataclass
class TargetConfig:
    path: str
    parser: Optional[str] = None
    min_severity: str = "warning"
    polling: bool = False
    multiline_pattern: Optional[str] = None
    tags: dict = field(default_factory=dict)


@dataclass
class SentinelConfig:
    sentry_dsn: str
    targets: list[TargetConfig]
    state_file: str = "~/.log-sentinel/state.json"
    glob_rescan_interval: int = 30
    dedup_window: int = 60
    breadcrumb_limit: int = 100
    health_check_port: int = 8099


def load_config(path: str) -> SentinelConfig:
    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    dsn = raw.get("sentry_dsn") or os.environ.get("SENTRY_DSN")
    if not dsn:
        raise ConfigError("sentry_dsn is required (config file or SENTRY_DSN env var)")

    raw_targets = raw.get("targets")
    if not raw_targets:
        raise ConfigError("At least one target is required")

    defaults = raw.get("defaults", {})

    targets = []
    for i, t in enumerate(raw_targets):
        if not t.get("path"):
            raise ConfigError(f"Target {i} missing required 'path' field")
        targets.append(TargetConfig(
            path=t["path"],
            parser=t.get("parser", defaults.get("parser")),
            min_severity=t.get("min_severity", defaults.get("min_severity", "warning")),
            polling=t.get("polling", defaults.get("polling", False)),
            multiline_pattern=t.get("multiline_pattern", defaults.get("multiline_pattern")),
            tags=t.get("tags", {}),
        ))

    return SentinelConfig(
        sentry_dsn=dsn,
        targets=targets,
        state_file=raw.get("state_file", "~/.log-sentinel/state.json"),
        glob_rescan_interval=raw.get("glob_rescan_interval", 30),
        dedup_window=raw.get("dedup_window", 60),
        breadcrumb_limit=raw.get("breadcrumb_limit", 100),
        health_check_port=raw.get("health_check_port", 8099),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: all pass.

- [ ] **Step 5: Create example config.yaml**

In `log-sentinel/config.yaml`:

```yaml
# Log Sentinel configuration
# sentry_dsn can also be set via SENTRY_DSN env var
sentry_dsn: "https://your-key@sentry.io/your-project-id"

defaults:
  min_severity: warning
  polling: false

targets:
  - path: "/var/log/syslog"
    parser: syslog
    min_severity: error
    tags:
      source: system

  - path: "/var/log/nginx/*.log"
    parser: clf
    min_severity: warning
    tags:
      service: nginx

  - path: "/opt/app/logs/**/*.json"
    parser: json
    min_severity: info
    multiline_pattern: "^\\{"
    tags:
      service: myapp

state_file: "~/.log-sentinel/state.json"
glob_rescan_interval: 30
dedup_window: 60
breadcrumb_limit: 100
health_check_port: 8099
```

- [ ] **Step 6: Commit**

```bash
git add log-sentinel/log_sentinel/config.py log-sentinel/tests/test_config.py log-sentinel/config.yaml
git commit -m "feat: add config loading with validation and example config"
```

---

## Task 9: Tailer (File Position Tracking, Rotation, Multi-line)

**Files:**
- Create: `log-sentinel/log_sentinel/tailer.py`
- Create: `log-sentinel/tests/test_tailer.py`

- [ ] **Step 1: Write failing tests**

In `tests/test_tailer.py`:

```python
import json
import os
import tempfile
import pytest
from log_sentinel.tailer import Tailer


class TestTailer:
    def setup_method(self):
        self.state_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.state_dir, "state.json")
        self.tailer = Tailer(self.state_file)

    def test_read_new_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("line 1\nline 2\nline 3\n")
            path = f.name
        lines = self.tailer.read_new_lines(path)
        assert lines == ["line 1", "line 2", "line 3"]
        os.unlink(path)

    def test_tracks_position(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("line 1\n")
            path = f.name

        self.tailer.read_new_lines(path)

        with open(path, "a") as f:
            f.write("line 2\n")

        lines = self.tailer.read_new_lines(path)
        assert lines == ["line 2"]
        os.unlink(path)

    def test_detects_truncation(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("line 1\nline 2\nline 3\n")
            path = f.name

        self.tailer.read_new_lines(path)

        # Truncate and write new content
        with open(path, "w") as f:
            f.write("new line 1\n")

        lines = self.tailer.read_new_lines(path)
        assert lines == ["new line 1"]
        os.unlink(path)

    def test_state_persistence(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("line 1\n")
            path = f.name

        self.tailer.read_new_lines(path)
        self.tailer.save_state()

        # Create new tailer from same state file
        tailer2 = Tailer(self.state_file)
        with open(path, "a") as f:
            f.write("line 2\n")

        lines = tailer2.read_new_lines(path)
        assert lines == ["line 2"]
        os.unlink(path)

    def test_atomic_state_write(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("line 1\n")
            path = f.name

        self.tailer.read_new_lines(path)
        self.tailer.save_state()

        assert os.path.exists(self.state_file)
        with open(self.state_file) as f:
            state = json.load(f)
        assert path in state
        os.unlink(path)

    def test_deleted_file_is_skipped(self):
        """Reading a deleted file returns empty list, no crash."""
        lines = self.tailer.read_new_lines("/nonexistent/file.log")
        assert lines == []

    def test_detects_inode_rotation(self):
        """Simulates log rotation: old file moved, new file at same path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, dir=self.state_dir) as f:
            f.write("old line 1\n")
            path = f.name

        self.tailer.read_new_lines(path)

        # Simulate rotation: delete old file, create new one at same path
        os.unlink(path)
        with open(path, "w") as f:
            f.write("rotated line 1\n")

        lines = self.tailer.read_new_lines(path)
        assert lines == ["rotated line 1"]


class TestMultiLine:
    def setup_method(self):
        self.state_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.state_dir, "state.json")
        self.tailer = Tailer(self.state_file)

    def test_multiline_with_pattern(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("2026-03-23 ERROR: something failed\n")
            f.write("  at module.function(file.py:10)\n")
            f.write("  at main(file.py:50)\n")
            f.write("2026-03-23 INFO: recovered\n")
            path = f.name

        # Pattern: lines starting with a date are new entries
        lines = self.tailer.read_new_lines(path, multiline_pattern=r"^\d{4}-\d{2}-\d{2}")
        assert len(lines) == 2
        assert "at module.function" in lines[0]
        assert lines[1] == "2026-03-23 INFO: recovered"
        os.unlink(path)

    def test_continuation_lines_default(self):
        """Without a pattern, each line is independent."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("line 1\n  continued\nline 2\n")
            path = f.name

        lines = self.tailer.read_new_lines(path)
        assert len(lines) == 3
        os.unlink(path)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_tailer.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: Write implementation**

In `log_sentinel/tailer.py`:

```python
import json
import os
import re
import tempfile
from typing import Optional


class Tailer:
    def __init__(self, state_file: str):
        self._state_file = os.path.expanduser(state_file)
        self._positions: dict[str, dict] = {}
        self._corrupt_recovery = False
        self._load_state()

    def _load_state(self):
        if os.path.exists(self._state_file):
            try:
                with open(self._state_file) as f:
                    self._positions = json.load(f)
            except (json.JSONDecodeError, OSError):
                import logging
                logging.getLogger("log-sentinel").warning(
                    "Corrupt state file %s — resetting to EOF for all files", self._state_file
                )
                self._positions = {}
                self._corrupt_recovery = True

    def save_state(self):
        state_dir = os.path.dirname(self._state_file)
        if state_dir:
            os.makedirs(state_dir, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(dir=state_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._positions, f)
            os.rename(tmp_path, self._state_file)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def read_new_lines(
        self,
        path: str,
        multiline_pattern: Optional[str] = None,
    ) -> list[str]:
        try:
            stat = os.stat(path)
        except OSError:
            import logging
            logging.getLogger("log-sentinel").warning("Cannot access %s — skipping", path)
            return []

        inode = stat.st_ino
        size = stat.st_size

        # On corrupt state recovery, skip to EOF for unknown files
        if self._corrupt_recovery and path not in self._positions:
            self._positions[path] = {"inode": inode, "offset": size}
            return []

        prev = self._positions.get(path, {})
        prev_inode = prev.get("inode")
        prev_offset = prev.get("offset", 0)

        # Detect rotation (inode change) or truncation (size shrink)
        if prev_inode != inode or size < prev_offset:
            prev_offset = 0

        if prev_offset >= size:
            return []

        try:
            with open(path, "r", errors="replace") as f:
                f.seek(prev_offset)
                raw = f.read()
                new_offset = f.tell()
        except OSError:
            return []

        self._positions[path] = {"inode": inode, "offset": new_offset}

        raw_lines = raw.splitlines()
        if not raw_lines:
            return []

        if multiline_pattern:
            return self._aggregate_multiline(raw_lines, multiline_pattern)
        return raw_lines

    @staticmethod
    def _aggregate_multiline(raw_lines: list[str], pattern: str) -> list[str]:
        compiled = re.compile(pattern)
        aggregated: list[str] = []
        current: list[str] = []

        for line in raw_lines:
            if compiled.match(line):
                if current:
                    aggregated.append("\n".join(current))
                current = [line]
            else:
                if current:
                    current.append(line)
                else:
                    # Orphan continuation line — treat as standalone
                    current = [line]

        if current:
            aggregated.append("\n".join(current))

        return aggregated

    def remove_file(self, path: str):
        self._positions.pop(path, None)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_tailer.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add log-sentinel/log_sentinel/tailer.py log-sentinel/tests/test_tailer.py
git commit -m "feat: add tailer with position tracking, rotation detection, multi-line"
```

---

## Task 10: Sentry Sender (Filtering, Dedup, Breadcrumbs)

**Files:**
- Create: `log-sentinel/log_sentinel/sender.py`
- Create: `log-sentinel/tests/test_sender.py`

- [ ] **Step 1: Write failing tests**

In `tests/test_sender.py`:

```python
import hashlib
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_sender.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: Write implementation**

In `log_sentinel/sender.py`:

```python
import hashlib
import socket
import time
from collections import defaultdict, deque

import sentry_sdk

from .parsers.base import LogEntry

SEVERITY_ORDER = {"debug": 0, "info": 1, "warning": 2, "error": 3}
SENTRY_LEVELS = {"error": "error", "warning": "warning", "info": "info", "debug": "debug"}


class SentrySender:
    def __init__(self, dedup_window: int, breadcrumb_limit: int):
        self._dedup_window = dedup_window
        self._breadcrumb_limit = breadcrumb_limit
        self._dedup_cache: dict[str, float] = {}
        self._dedup_counts: dict[str, int] = {}
        self._breadcrumbs: dict[str, deque] = defaultdict(deque)
        self._hostname = socket.gethostname()
        self.metrics = {
            "lines_processed": 0,
            "events_sent": 0,
            "parse_failures": 0,
        }

    def send(self, entry: LogEntry, min_severity: str, tags: dict, parser_name: str = "auto"):
        self.metrics["lines_processed"] += 1

        entry_level = SEVERITY_ORDER.get(entry.severity, 1)
        min_level = SEVERITY_ORDER.get(min_severity, 2)

        if entry_level < min_level:
            return

        # Info/debug → breadcrumb, not an event
        if entry.severity in ("info", "debug"):
            self._add_breadcrumb(entry)
            return

        # Dedup check
        fingerprint = self._fingerprint(entry)
        now = time.monotonic()
        self._expire_dedup(now)

        if fingerprint in self._dedup_cache:
            self._dedup_counts[fingerprint] = self._dedup_counts.get(fingerprint, 0) + 1
            return

        self._dedup_cache[fingerprint] = now
        suppressed_count = self._dedup_counts.pop(fingerprint, 0)

        # Flush breadcrumbs for this source before sending event
        self._flush_breadcrumbs(entry.source_file)

        all_tags = {
            "log.source": entry.source_file,
            "log.parser": parser_name,
            "log.host": self._hostname,
            **tags,
        }

        with sentry_sdk.push_scope() as scope:
            for k, v in all_tags.items():
                scope.set_tag(k, v)
            context = dict(entry.extra_fields) if entry.extra_fields else {}
            if suppressed_count > 0:
                context["duplicate_count"] = suppressed_count
            if context:
                scope.set_context("log_entry", context)

            sentry_sdk.capture_message(
                entry.message,
                level=SENTRY_LEVELS.get(entry.severity, "error"),
            )

        self.metrics["events_sent"] += 1

    def _fingerprint(self, entry: LogEntry) -> str:
        raw = f"{entry.severity}:{entry.source_file}:{entry.message}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _expire_dedup(self, now: float):
        expired = [k for k, t in self._dedup_cache.items() if now - t > self._dedup_window]
        for k in expired:
            del self._dedup_cache[k]

    def _add_breadcrumb(self, entry: LogEntry):
        bc = {
            "message": entry.message,
            "level": entry.severity,
            "timestamp": entry.timestamp.isoformat(),
            "data": entry.extra_fields,
        }
        buf = self._breadcrumbs[entry.source_file]
        buf.append(bc)
        while len(buf) > self._breadcrumb_limit:
            buf.popleft()

    def _flush_breadcrumbs(self, source_file: str):
        buf = self._breadcrumbs.get(source_file)
        if not buf:
            return
        for bc in buf:
            sentry_sdk.add_breadcrumb(
                message=bc["message"],
                level=bc["level"],
                timestamp=bc["timestamp"],
                data=bc.get("data"),
            )
        buf.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_sender.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add log-sentinel/log_sentinel/sender.py log-sentinel/tests/test_sender.py
git commit -m "feat: add Sentry sender with severity filtering, dedup, breadcrumbs"
```

---

## Task 11: Watcher (Filesystem Monitoring + Glob Re-expansion)

**Files:**
- Create: `log-sentinel/log_sentinel/watcher.py`

- [ ] **Step 1: Write implementation**

Note: The watcher is hard to unit test in isolation due to filesystem event timing. It will be tested via the integration test in Task 13. We build it now and verify it works in integration.

In `log_sentinel/watcher.py`:

```python
import glob
import logging
import threading
import time
from typing import Callable

from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent

logger = logging.getLogger("log-sentinel")


class LogFileHandler(FileSystemEventHandler):
    def __init__(self, callback: Callable[[str], None], watched_files: set[str]):
        self._callback = callback
        self._watched_files = watched_files

    def on_modified(self, event):
        if not event.is_directory and event.src_path in self._watched_files:
            self._callback(event.src_path)

    def on_created(self, event):
        if not event.is_directory and event.src_path in self._watched_files:
            self._callback(event.src_path)


class Watcher:
    def __init__(
        self,
        targets: list[dict],
        on_file_changed: Callable[[str, dict], None],
        glob_rescan_interval: int = 30,
    ):
        self._targets = targets
        self._on_file_changed = on_file_changed
        self._glob_rescan_interval = glob_rescan_interval
        self._observers: list[Observer] = []
        self._watched_files: dict[str, dict] = {}  # path → target config
        self._stop_event = threading.Event()

    def start(self):
        self._expand_globs()
        self._start_observers()

        self._rescan_thread = threading.Thread(target=self._rescan_loop, daemon=True)
        self._rescan_thread.start()

    def stop(self):
        self._stop_event.set()
        for obs in self._observers:
            obs.stop()
        for obs in self._observers:
            obs.join(timeout=5)

    def _expand_globs(self):
        for target in self._targets:
            pattern = target["path"]
            matches = glob.glob(pattern, recursive=True)
            for path in matches:
                if path not in self._watched_files:
                    self._watched_files[path] = target
                    logger.info("Watching: %s", path)

    def _start_observers(self):
        # Group files by directory and polling mode
        dirs: dict[tuple[str, bool], set[str]] = {}
        for path, target in self._watched_files.items():
            import os
            d = os.path.dirname(path)
            polling = target.get("polling", False)
            key = (d, polling)
            dirs.setdefault(key, set()).add(path)

        for (directory, polling), files in dirs.items():
            handler = LogFileHandler(
                callback=lambda p: self._on_file_changed(p, self._watched_files.get(p, {})),
                watched_files=files,
            )
            obs = PollingObserver() if polling else Observer()
            obs.schedule(handler, directory, recursive=False)
            obs.daemon = True
            obs.start()
            self._observers.append(obs)

    def _rescan_loop(self):
        while not self._stop_event.wait(self._glob_rescan_interval):
            old_count = len(self._watched_files)
            self._expand_globs()
            new_count = len(self._watched_files)
            if new_count > old_count:
                # Restart observers to pick up new directories
                for obs in self._observers:
                    obs.stop()
                self._observers.clear()
                self._start_observers()
```

- [ ] **Step 2: Commit**

```bash
git add log-sentinel/log_sentinel/watcher.py
git commit -m "feat: add watcher with watchdog observers and glob re-expansion"
```

---

## Task 12: Health Check Endpoint

**Files:**
- Create: `log-sentinel/log_sentinel/health.py`

- [ ] **Step 1: Write implementation**

In `log_sentinel/health.py`:

```python
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable


class HealthHandler(BaseHTTPRequestHandler):
    metrics_fn: Callable[[], dict] = lambda: {}

    def do_GET(self):
        if self.path == "/health":
            data = self.metrics_fn()
            body = json.dumps({"status": "ok", **data}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default logging


class HealthServer:
    def __init__(self, port: int, metrics_fn: Callable[[], dict]):
        self._port = port
        self._metrics_fn = metrics_fn
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self):
        if self._port == 0:
            return

        handler = type("H", (HealthHandler,), {"metrics_fn": staticmethod(self._metrics_fn)})
        self._server = HTTPServer(("0.0.0.0", self._port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server:
            self._server.shutdown()
```

- [ ] **Step 2: Commit**

```bash
git add log-sentinel/log_sentinel/health.py
git commit -m "feat: add HTTP health check endpoint"
```

---

## Task 13: Daemon Runner (Main Entry Point)

**Files:**
- Create: `log-sentinel/log_sentinel/__main__.py`

- [ ] **Step 1: Write implementation**

In `log_sentinel/__main__.py`:

```python
import argparse
import logging
import signal
import sys
import threading

import sentry_sdk

from .config import load_config
from .tailer import Tailer
from .sender import SentrySender
from .watcher import Watcher
from .health import HealthServer
from .parsers import parse_line

logger = logging.getLogger("log-sentinel")


def main():
    parser = argparse.ArgumentParser(description="Log Sentinel — log file to Sentry forwarder")
    parser.add_argument("-c", "--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--backfill", action="store_true", help="Replay from beginning of files")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    config = load_config(args.config)
    logger.info("Loaded config with %d targets", len(config.targets))

    sentry_sdk.init(dsn=config.sentry_dsn)

    tailer = Tailer(config.state_file)
    if not args.backfill:
        tailer.skip_to_eof = True  # First read of unknown files will seek to EOF

    sender = SentrySender(
        dedup_window=config.dedup_window,
        breadcrumb_limit=config.breadcrumb_limit,
    )

    # Build target lookup for watcher callbacks
    target_configs = []
    for t in config.targets:
        target_configs.append({
            "path": t.path,
            "parser": t.parser,
            "min_severity": t.min_severity,
            "polling": t.polling,
            "multiline_pattern": t.multiline_pattern,
            "tags": t.tags,
        })

    def on_file_changed(path: str, target: dict):
        try:
            lines = tailer.read_new_lines(path, multiline_pattern=target.get("multiline_pattern"))
            for line in lines:
                entry = parse_line(line, path, parser_hint=target.get("parser"))
                if entry:
                    sender.send(
                        entry,
                        min_severity=target.get("min_severity", "warning"),
                        tags=target.get("tags", {}),
                        parser_name=target.get("parser") or "auto",
                    )
                else:
                    sender.metrics["parse_failures"] += 1
        except Exception:
            logger.exception("Error processing %s", path)

        tailer.save_state()

    watcher = Watcher(
        targets=target_configs,
        on_file_changed=on_file_changed,
        glob_rescan_interval=config.glob_rescan_interval,
    )

    health = HealthServer(port=config.health_check_port, metrics_fn=lambda: sender.metrics)

    stop_event = threading.Event()

    def shutdown(signum, frame):
        logger.info("Shutting down (signal %s)...", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    watcher.start()
    health.start()
    logger.info("Log Sentinel started")

    try:
        stop_event.wait()
    finally:
        watcher.stop()
        health.stop()
        tailer.save_state()
        logger.info("Log Sentinel stopped")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add log-sentinel/log_sentinel/__main__.py
git commit -m "feat: add daemon runner with signal handling and health check"
```

---

## Task 14: Integration Test

**Files:**
- Create: `log-sentinel/tests/test_integration.py`

- [ ] **Step 1: Write integration test**

In `tests/test_integration.py`:

```python
import json
import os
import tempfile
import threading
import time

import yaml
import sentry_sdk
from sentry_sdk.transport import Transport

from log_sentinel.config import load_config
from log_sentinel.tailer import Tailer
from log_sentinel.sender import SentrySender
from log_sentinel.parsers import parse_line


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

        # Write an error line
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
```

- [ ] **Step 2: Run all tests**

```bash
cd /opt/logs/log-sentinel
source venv/bin/activate
pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add log-sentinel/tests/test_integration.py
git commit -m "feat: add integration tests for end-to-end pipeline"
```

---

## Task 15: systemd Unit File

**Files:**
- Create: `log-sentinel/log-sentinel.service`

- [ ] **Step 1: Create the unit file**

In `log-sentinel/log-sentinel.service`:

```ini
[Unit]
Description=Log Sentinel — log file to Sentry forwarder
After=network.target

[Service]
Type=simple
User=log-sentinel
Group=log-sentinel
ExecStart=/opt/log-sentinel/venv/bin/python -m log_sentinel -c /etc/log-sentinel/config.yaml
Restart=on-failure
RestartSec=5
StandardError=journal

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ReadOnlyPaths=/var/log
ReadWritePaths=/home/log-sentinel/.log-sentinel

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Commit**

```bash
git add log-sentinel/log-sentinel.service
git commit -m "feat: add systemd unit file with security hardening"
```

---

## Task 16: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
cd /opt/logs/log-sentinel
source venv/bin/activate
pytest -v --tb=short
```

Expected: all tests pass.

- [ ] **Step 2: Verify package installs cleanly**

```bash
pip install -e ".[dev]"
python -m log_sentinel --help
```

Expected: help text printed.

- [ ] **Step 3: Verify git log**

```bash
git log --oneline
```

Expected: clean sequence of commits from scaffolding through final tests.

---

## Task 17: Tailer Skip-to-EOF Support (for non-backfill startup)

**Files:**
- Modify: `log-sentinel/log_sentinel/tailer.py`
- Modify: `log-sentinel/tests/test_tailer.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_tailer.py`:

```python
    def test_skip_to_eof_on_first_read(self):
        """When skip_to_eof is set, first read of unknown files seeks to EOF."""
        tailer = Tailer(self.state_file)
        tailer.skip_to_eof = True

        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("old line 1\nold line 2\n")
            path = f.name

        # First read should skip existing content
        lines = tailer.read_new_lines(path)
        assert lines == []

        # New content after skip should be read
        with open(path, "a") as f:
            f.write("new line\n")

        lines = tailer.read_new_lines(path)
        assert lines == ["new line"]
        os.unlink(path)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_tailer.py::TestTailer::test_skip_to_eof_on_first_read -v
```

Expected: FAIL — `AttributeError: skip_to_eof`

- [ ] **Step 3: Update tailer implementation**

Add `skip_to_eof` attribute to `__init__` and check it in `read_new_lines`:

In `__init__`:
```python
    self.skip_to_eof = False
```

In `read_new_lines`, after the corrupt recovery check, before the `prev = self._positions.get(...)` line:
```python
        # Skip to EOF for first-time files when not in backfill mode
        if self.skip_to_eof and path not in self._positions:
            self._positions[path] = {"inode": inode, "offset": size}
            return []
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_tailer.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add log-sentinel/log_sentinel/tailer.py log-sentinel/tests/test_tailer.py
git commit -m "feat: add skip-to-EOF for non-backfill startup mode"
```

---

## Task 18: Health Endpoint Tests

**Files:**
- Modify: `log-sentinel/tests/test_integration.py`

- [ ] **Step 1: Write test**

Append to `tests/test_integration.py`:

```python
import urllib.request
from log_sentinel.health import HealthServer


class TestHealthEndpoint:
    def test_health_returns_metrics(self):
        metrics = {"lines_processed": 42, "events_sent": 5, "parse_failures": 1}
        server = HealthServer(port=0, metrics_fn=lambda: metrics)
        # Use port 0 — disabled, so test the handler directly
        # For a real test, use a random port:
        server_real = HealthServer(port=18099, metrics_fn=lambda: metrics)
        server_real.start()
        try:
            resp = urllib.request.urlopen("http://127.0.0.1:18099/health")
            data = json.loads(resp.read())
            assert data["status"] == "ok"
            assert data["lines_processed"] == 42
            assert data["events_sent"] == 5
        finally:
            server_real.stop()

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
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_integration.py::TestHealthEndpoint -v
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add log-sentinel/tests/test_integration.py
git commit -m "test: add health endpoint tests"
```

---

## Task 19: Final Test Suite Run

- [ ] **Step 1: Run full test suite**

```bash
cd /opt/logs/log-sentinel
source venv/bin/activate
pytest -v --tb=short
```

Expected: all tests pass.

- [ ] **Step 2: Commit any final fixes if needed**

---

## Notes

**Deferred items (not in scope for v0.1):**
- RFC 5424 syslog format support
- journald source (binary format, needs `systemd.journal.Reader`)
- Sentry unavailability resilience (bounded queue, exponential backoff retry) — for low volume this is not critical; the SDK has its own transport queue
- Default multi-line continuation patterns for the fallback parser path (whitespace/`Caused by:` lines) — can be added when specific log sources need it
