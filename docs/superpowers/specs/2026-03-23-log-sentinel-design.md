# Log Sentinel — Design Spec

**Date:** 2026-03-23
**Status:** Approved

## Overview

A Python daemon (`log-sentinel`) that watches log files in real-time and sends events to Sentry.io for error detection, observability, and incident correlation.

## Requirements

- Monitor mixed log sources: application logs, system logs (syslog, journald), and third-party service logs (nginx, postgres, etc.)
- Handle mixed formats: JSON, syslog, common log format, and unstructured free-text
- Run as a long-lived daemon (systemd-compatible)
- Low volume (~few MB/day)
- Sentry project and DSN already available

## Architecture

```
┌─────────────┐     ┌──────────┐     ┌────────────┐     ┌─────────┐
│ Log Files   │────▶│ Watcher  │────▶│  Parsers   │────▶│ Sentry  │
│ (mixed fmt) │     │(watchdog)│     │(chain-of-  │     │  SDK    │
└─────────────┘     └──────────┘     │ responsibility)   └─────────┘
                         │           └────────────┘
                         ▼
                    ┌──────────┐
                    │ State DB │
                    │(positions│
                    │ offsets) │
                    └──────────┘
```

## Components

### 1. Configuration (`config.yaml`)

- **Sentry DSN**: from config or `SENTRY_DSN` env var
- **Watch targets**: list of file paths or glob patterns (e.g., `/var/log/syslog`, `/var/log/nginx/*.log`, `/opt/app/logs/**/*.json`)
- **Per-target overrides**: optional parser hint, custom tags, severity mapping
- **Global settings**: polling interval fallback, state file path, daemon log level

### 2. Watcher (`watcher.py`)

- Uses `watchdog.observers.Observer` to monitor directories for `FileModifiedEvent`
- On modification, hands off to the tailer
- Detects log rotation via inode change or file shrink — resets position
- Fallback polling mode for filesystems where inotify isn't available (e.g., NFS)

### 3. Tailer (`tailer.py`)

- Tracks read positions per file in a JSON state file (`~/.log-sentinel/state.json`)
- On file change, seeks to last known position, reads new lines, updates position
- Handles: file truncation, file deletion, new files matching glob patterns

### 4. Parser Chain (`parsers/`)

Chain-of-responsibility pattern, tried in order:

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

- **ERROR/FATAL** → `capture_message()` or `capture_exception()` with tags
- **WARNING** → `capture_message(level="warning")`
- **INFO/DEBUG** → accumulated as breadcrumbs, flushed periodically (default 5 min) or when an error occurs
- Tags: `log.source`, `log.parser`, `log.host`

### 6. Daemon Runner (`main.py`)

- Entry point: loads config, initializes components
- Graceful shutdown on SIGTERM/SIGINT
- Runnable via systemd unit file (provided) or directly

## Error Handling & Resilience

- **Sentry unavailable**: bounded in-memory queue (default 1000 entries), exponential backoff retry, drop oldest if full
- **Malformed log lines**: skip, increment `parse_failures` counter tag
- **File permission errors**: warn to stderr, skip file, continue watching others
- **State file corruption**: reset to end-of-file for all files, warn
- **Crash recovery**: resume from state file positions on startup; no state file → start from current EOF; `--backfill` flag for full replay

## Testing Strategy

- **Unit tests**: each parser against sample log lines (valid, malformed, edge cases); tailer with mock files; sender with mocked Sentry SDK
- **Integration test**: write lines to temp file, assert Sentry events captured (using SDK transport override)
- **Config validation test**: bad configs fail fast with clear errors

## Tech Stack

- Python 3.10+
- `watchdog` — filesystem monitoring
- `sentry-sdk` — Sentry integration
- `pyyaml` — configuration
- `pytest` — testing

## File Structure

```
log-sentinel/
├── config.yaml
├── main.py
├── watcher.py
├── tailer.py
├── sender.py
├── parsers/
│   ├── __init__.py
│   ├── base.py          # LogEntry dataclass, BaseParser ABC
│   ├── json_parser.py
│   ├── syslog_parser.py
│   ├── clf_parser.py
│   └── fallback_parser.py
├── tests/
│   ├── test_parsers.py
│   ├── test_tailer.py
│   ├── test_sender.py
│   └── test_integration.py
├── log-sentinel.service  # systemd unit file
└── requirements.txt
```
