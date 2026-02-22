"""
logger.py - Per-manager rotating log files.

Each manager gets its own log file in ~/.claude/super-manager/logs/.
Files rotate at 1MB, keeping 3 old copies.

Usage:
    from shared.logger import create_logger
    log = create_logger("hook-manager")
    log.info("Added hook: my-hook")
    log.error("File not found: path/to/hook.js")
"""
import os
import datetime
from shared.configuration_paths import LOGS_DIR

MAX_LOG_SIZE = 1_000_000  # 1MB
MAX_ROTATIONS = 3


def _ensure_logs_dir():
    os.makedirs(LOGS_DIR, exist_ok=True)


def _rotate_if_needed(log_path):
    """Rotate log file if it exceeds MAX_LOG_SIZE."""
    if not os.path.exists(log_path):
        return
    if os.path.getsize(log_path) < MAX_LOG_SIZE:
        return
    # Rotate: .log.3 -> delete, .log.2 -> .log.3, .log.1 -> .log.2, .log -> .log.1
    for i in range(MAX_ROTATIONS, 0, -1):
        old = f"{log_path}.{i}"
        new = f"{log_path}.{i + 1}" if i < MAX_ROTATIONS else None
        if os.path.exists(old):
            if new:
                os.replace(old, new)
            else:
                os.remove(old)
    os.replace(log_path, f"{log_path}.1")


class Logger:
    def __init__(self, manager_name):
        self.manager_name = manager_name
        self.log_path = os.path.join(LOGS_DIR, f"{manager_name}.log")
        _ensure_logs_dir()

    def _write(self, level, message):
        _rotate_if_needed(self.log_path)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{timestamp} [{level}] [{self.manager_name}] {message}\n"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line)

    def info(self, message):
        self._write("INFO", message)

    def warn(self, message):
        self._write("WARN", message)

    def error(self, message):
        self._write("ERROR", message)

    def debug(self, message):
        self._write("DEBUG", message)


def create_logger(manager_name):
    """Create a logger for a specific manager. Logs to ~/.claude/super-manager/logs/{name}.log"""
    return Logger(manager_name)
