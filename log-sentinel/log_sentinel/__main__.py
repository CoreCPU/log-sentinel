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

    sentry_sdk.init(dsn=config.sentry_dsn, enable_logs=True)

    tailer = Tailer(config.state_file)
    if not args.backfill:
        tailer.skip_to_eof = True

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
