"""
file_operations.py - Archive-not-delete and atomic write operations.

NEVER deletes files. Always moves to ~/.claude/super-manager/archive/ with a timestamp.
Atomic writes use temp-file-then-rename to prevent corruption.
"""
import os
import shutil
import datetime
from shared.configuration_paths import ARCHIVE_DIR


def _ensure_archive_dir():
    os.makedirs(ARCHIVE_DIR, exist_ok=True)


def archive_file(source_path, reason=""):
    """
    Move a file to the archive directory with a timestamp suffix.
    Example: hook.js -> archive/hook.js_20260214_195500
    Returns the archive path, or None if source doesn't exist.
    """
    if not os.path.exists(source_path):
        return None
    _ensure_archive_dir()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = os.path.basename(source_path)
    archive_name = f"{basename}_{timestamp}"
    if reason:
        archive_name += f"_{reason}"
    archive_path = os.path.join(ARCHIVE_DIR, archive_name)
    shutil.move(source_path, archive_path)
    return archive_path


def archive_directory(source_path, reason=""):
    """Move a directory to the archive with a timestamp suffix."""
    if not os.path.exists(source_path):
        return None
    _ensure_archive_dir()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = os.path.basename(source_path)
    archive_name = f"{basename}_{timestamp}"
    if reason:
        archive_name += f"_{reason}"
    archive_path = os.path.join(ARCHIVE_DIR, archive_name)
    shutil.move(source_path, archive_path)
    return archive_path


def atomic_write(file_path, content):
    """Write content to file atomically (write to .tmp, then rename)."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    tmp_path = file_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, file_path)


def ensure_directory(dir_path):
    """Create directory and parents if they don't exist."""
    os.makedirs(dir_path, exist_ok=True)
