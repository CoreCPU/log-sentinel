import glob
import logging
import os
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
