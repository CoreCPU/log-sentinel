# Log Sentinel — Design Spec

**Date:** 2026-03-23
**Status:** Approved (rev 2 — post-review)

## Overview

A Python daemon (`log-sentinel`) that watches log files in real-time and sends events to Sentry.io for error detection, observability, and incident correlation.

## Requirements

- Monitor mixed log sources: application logs, system logs (syslog), and third-party service logs (nginx, postgres, etc.)
- Handle mixed formats: JSON, syslog, common log format, and unstructured free-text
- Run as a long-lived daemon (systemd-compatible)
- Low volume (~few MB/day)
- Sentry project and DSN already available

**Out of scope:** journald (binary format requiring `systemd.journal.Reader` — may be added as a future extension with a dedicated source component).

## Architecture

```
┌─────────────┐     ┌──────────┐     ┌───────────┐     ┌────────────┐     ┌─────────┐
│ Log Files   │────▶│ Watcher  │────▶│  Tailer   │────▶│  Parsers   │────▶│ Sender  │
│ (mixed fmt) │     │(watchdog)│     │(positions)│     │(chain-of-  │     │(Sentry  │
└─────────────┘     └──────────┘     └───────────┘     │ responsibility)   │  SDK)   │
                                          │            └────────────┘     └─────────┘
                                          ▼
                                     ┌──────────┐
                                     │ State DB │
                                     │(atomic   │
                                     │ JSON)    │
                                     └──────────┘
```

### Component Responsibilities (clear ownership)

- **Watcher** owns: filesystem event monitoring, directory scanning, glob re-expansion
- **Tailer** owns: file read positions, rotation/truncation detection, multi-line aggregation, state persistence
- **Parsers** own: line → `LogEntry` transformation
- **Sender** owns: Sentry API interaction, severity filtering, deduplication, breadcrumb management

## Components

### 1. Configuration (`config.yaml`)

```yaml
sentry_dsn: "https://..."  # or use SENTRY_DSN env var

defaults:
  min_severity: warning          # global default: only warning+ sent to Sentry
  polling: false                 # true for NFS/network filesystems
  multiline_pattern: null        # regex for multi-line start detection

targets:
  - path: "/var/log/syslog"
    parser: syslog               # optional parser hint (auto-detect if omitted)
    min_severity: error           # override: only errors from syslog
    tags:
      environment: production

  - path: "/var/log/nginx/*.log"
    parser: clf
    min_severity: warning
    tags:
      service: nginx

  - path: "/opt/app/logs/**/*.json"
    parser: json
    min_severity: info
    multiline_pattern: "^\\{"    # JSON objects start with {
    tags:
      service: myapp

state_file: "~/.log-sentinel/state.json"
glob_rescan_interval: 30         # seconds between glob re-expansion
dedup_window: 60                 # seconds; suppress duplicate messages within window
breadcrumb_limit: 100            # max breadcrumbs held in memory per source
health_check_port: 8099          # 0 to disable
```

**Required fields:** `sentry_dsn` (or env var), at least one target with `path`.
**All other fields** have defaults as shown above. Config is validated at startup; invalid config fails fast with clear error messages.

### 2. Watcher (`watcher.py`)

- Uses `watchdog.observers.Observer` (inotify on Linux) to monitor directories for `FileModifiedEvent` and `FileCreatedEvent`
- Per-target `polling: true` config flag switches to `PollingObserver` for NFS/network filesystems
- **Glob re-expansion**: periodically re-evaluates glob patterns (configurable interval, default 30s) to discover new files; registers new files with the tailer
- On file events, delegates to the tailer for reading

### 3. Tailer (`tailer.py`)

- Tracks read positions per file in state file
- **Rotation detection** (sole owner): tracks file inode + size; inode change or size shrink → reset position to 0
- **Multi-line aggregation**: configurable `multiline_pattern` regex per target; lines not matching the pattern are appended to the previous entry. Default patterns for known parsers:
  - Fallback parser: lines starting with whitespace or `Caused by:` are continuation lines
  - JSON parser: accumulate until valid JSON or blank line
- **Atomic state writes**: write to temp file, then `os.rename()` to target path (atomic on POSIX)
- On file change: seek to last position, read new lines, aggregate multi-line entries, pass to parser chain

### 4. Parser Chain (`parsers/`)

Chain-of-responsibility pattern, tried in order (unless parser hint is set in config):

1. **`json_parser.py`** — `json.loads()`, extracts `level`/`message`/`timestamp`
2. **`syslog_parser.py`** — regex for RFC 3164/5424 syslog format
3. **`clf_parser.py`** — Common/Combined Log Format (nginx, Apache); HTTP 5xx → error, 4xx → warning
4. **`fallback_parser.py`** — keyword detection (`ERROR`, `WARN`, `FATAL`, `Exception`, `Traceback`)

All parsers return a normalized `LogEntry` dataclass:
- `timestamp`: datetime
- `severity`: str (error, warning, info, debug)
- `message`: str
- `source_file`: str
- `extra_fields`: dict

### 5. Sentry Sender (`sender.py`)

**Severity filtering**: each `LogEntry` is checked against the target's `min_severity`. Entries below threshold are discarded.

**Event mapping** (all use `capture_message()` — no `capture_exception()` since there's no Python exception context):
- **ERROR/FATAL** → `capture_message(level="error")` with tags and `extra_fields` as Sentry event context
- **WARNING** → `capture_message(level="warning")` with tags and context

**Breadcrumb handling**:
- **INFO/DEBUG** entries (that pass severity filter) are accumulated as breadcrumbs, scoped per source file
- Bounded to `breadcrumb_limit` per source (default 100); oldest discarded when full
- Breadcrumbs are attached to the next error/warning event from the same source
- If no error occurs, breadcrumbs are simply bounded and rolled over — they are not sent independently (this is how Sentry breadcrumbs work)

**Client-side deduplication**: fingerprint each message (hash of severity + source + normalized message). Suppress duplicates within `dedup_window` (default 60s). Count suppressed occurrences; include count in the next sent event as `duplicate_count` context field.

**Tags on every event**: `log.source`, `log.parser`, `log.host`, plus any per-target custom tags.

### 6. Daemon Runner (`main.py`)

- Entry point: loads and validates config, initializes components
- Graceful shutdown on SIGTERM/SIGINT
- **Health check**: optional HTTP endpoint (default port 8099) returning JSON status: `{"status": "ok", "lines_processed": N, "events_sent": N, "parse_failures": N, "queue_depth": N}`
- Daemon logs its own operations to stderr (separate from watched logs)
- Runnable via systemd unit file or directly

### 7. systemd Unit File (`log-sentinel.service`)

```ini
[Unit]
Description=Log Sentinel — log file to Sentry forwarder
After=network.target

[Service]
Type=simple
User=log-sentinel
Group=log-sentinel
ExecStart=/opt/log-sentinel/venv/bin/python -m log_sentinel
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

A dedicated `log-sentinel` system user with read access to watched log paths.

## Error Handling & Resilience

- **Sentry unavailable**: bounded in-memory queue (default 1000 entries), exponential backoff retry, drop oldest if full
- **Malformed log lines**: skip, increment `parse_failures` counter (visible in health endpoint)
- **File permission errors**: warn to stderr, skip file, continue watching others
- **State file corruption**: atomic writes prevent partial state; if corruption still occurs, reset to EOF for all files, warn
- **Crash recovery**: resume from state file positions on startup; no state file → start from current EOF
- **`--backfill` flag**: replay from beginning of files; respects a throttle (max N events/second) to avoid Sentry quota burst

## Testing Strategy

- **Unit tests**: each parser against sample log lines (valid, malformed, edge cases, multi-line); tailer with mock files including rotation and truncation; sender with mocked Sentry SDK including dedup and breadcrumb logic
- **Integration test**: write lines to temp file, assert Sentry events captured (using SDK `transport` override to capture locally)
- **Config validation test**: bad configs fail fast with clear errors
- **Multi-line test**: verify stack traces and multi-line JSON are correctly aggregated

## Tech Stack

- Python 3.10+
- `watchdog` — filesystem monitoring
- `sentry-sdk` — Sentry integration
- `pyyaml` — configuration
- `pytest` — testing

## File Structure

```
log-sentinel/
├── pyproject.toml
├── config.yaml
├── log_sentinel/
│   ├── __init__.py
│   ├── __main__.py       # entry point
│   ├── config.py         # config loading and validation
│   ├── watcher.py
│   ├── tailer.py
│   ├── sender.py
│   ├── health.py         # HTTP health check endpoint
│   └── parsers/
│       ├── __init__.py
│       ├── base.py       # LogEntry dataclass, BaseParser ABC
│       ├── json_parser.py
│       ├── syslog_parser.py
│       ├── clf_parser.py
│       └── fallback_parser.py
├── tests/
│   ├── test_parsers.py
│   ├── test_tailer.py
│   ├── test_sender.py
│   └── test_integration.py
├── log-sentinel.service
└── requirements.txt
```
