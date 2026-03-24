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
