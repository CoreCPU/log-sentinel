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
