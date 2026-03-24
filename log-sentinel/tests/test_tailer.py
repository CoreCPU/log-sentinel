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
