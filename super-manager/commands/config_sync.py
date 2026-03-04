"""
config_sync.py - Config import/export/uninstall orchestrator.

Thin orchestrator that reads manifest.json from config repos, runs conflict
analysis, and delegates install/uninstall to per-manager setup.js/uninstall.js.

Usage (via super_manager.py):
  config import <owner/repo>         First-time install from repo
  config import                      Update from all registered repos
  config import --headless           Auto-approve ALL including conflicts
  config import --headless-safe      Auto-approve, skip conflicts
  config export <owner/repo>         Push local config to repo
  config uninstall <owner/repo>      Remove repo's items, restore originals
  config uninstall --all             Remove everything, full restore
  config add-repo <owner/repo>       Register a config repo source
  config remove-repo <owner/repo>    Unregister (archive, not delete)
  config repos                       List registered config repos
  config review                      Review pending conflicts
  config status                      What's installed, from which repos
  config restore <backup-id>         Restore to specific backup
  config restore --list              List available backups
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.configuration_paths import (
    CLAUDE_DIR,
    CONFIG_BACKUPS_DIR,
    CONFIG_DIR,
    CONFIG_INSTALLED_JSON,
    CONFIG_PENDING_JSON,
    CONFIG_REPOS_DIR,
    CONFIG_REPOS_JSON,
    DEFAULT_CONFIG_REPO,
    GLOBAL_SKILLS_DIR,
    HOOKS_DIR,
    RULES_DIR,
    SETTINGS_JSON,
    SUPER_MANAGER_DIR,
)
from shared.logger import create_logger

log = create_logger("config-sync")

# -------------------------------------------------------------------------
# Path helpers
# -------------------------------------------------------------------------


def _resolve_path(target):
    """Expand ~ and env vars in a target path. Returns None if target is None."""
    if target is None:
        return None
    return os.path.expanduser(os.path.expandvars(target))


def _repo_slug(owner_repo):
    """Convert 'owner/repo' to 'owner--repo' for filesystem use."""
    return owner_repo.replace("/", "--")


def _repo_clone_dir(owner_repo):
    """Path to the local clone of a config repo."""
    return os.path.join(CONFIG_REPOS_DIR, _repo_slug(owner_repo))


def _ensure_dirs():
    """Create config directory structure if needed."""
    for d in [CONFIG_DIR, CONFIG_REPOS_DIR, CONFIG_BACKUPS_DIR]:
        os.makedirs(d, exist_ok=True)


# -------------------------------------------------------------------------
# Checksum computation
# -------------------------------------------------------------------------


def compute_file_checksum(file_path):
    """SHA256 checksum of a single file."""
    h = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return "sha256:" + h.hexdigest()
    except (IOError, OSError):
        return None


def compute_dir_checksum(dir_path):
    """SHA256 checksum of a directory (sorted file contents concatenated)."""
    h = hashlib.sha256()
    if not os.path.isdir(dir_path):
        return None
    for root, dirs, files in os.walk(dir_path):
        dirs.sort()
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, dir_path)
            h.update(rel.encode("utf-8"))
            try:
                with open(fpath, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        h.update(chunk)
            except (IOError, OSError):
                pass
    return "sha256:" + h.hexdigest()


# -------------------------------------------------------------------------
# Manifest parsing and validation
# -------------------------------------------------------------------------


def parse_manifest(manifest_path):
    """Load and return manifest.json contents."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_manifest(manifest):
    """Validate manifest structure. Returns list of error strings (empty = valid)."""
    errors = []
    if "version" not in manifest:
        errors.append("Missing 'version' field")
    if "categories" not in manifest:
        errors.append("Missing 'categories' field")
        return errors
    cats = manifest["categories"]
    if not isinstance(cats, dict):
        errors.append("'categories' must be a dict")
        return errors
    for cat_name, cat_config in cats.items():
        if "path" not in cat_config:
            errors.append(f"Category '{cat_name}': missing 'path'")
        if "merge_strategy" not in cat_config:
            errors.append(f"Category '{cat_name}': missing 'merge_strategy'")
        if "items" not in cat_config:
            errors.append(f"Category '{cat_name}': missing 'items'")
        elif not isinstance(cat_config["items"], dict):
            errors.append(f"Category '{cat_name}': 'items' must be a dict")
    return errors


# -------------------------------------------------------------------------
# Conflict analyzer
# -------------------------------------------------------------------------


class ConflictReport:
    """Result of analyzing manifest against user's existing system."""

    def __init__(self):
        self.to_add = []      # items to install (not on user's system)
        self.up_to_date = []  # items matching checksum (already installed correctly)
        self.conflicts = []   # items user has customized (different checksum)
        self.to_merge = []    # registry items needing entry-level merge
        self.preserved = []   # user's files NOT in manifest (left untouched)
        self.existing_systems = []  # hooks/configs from other systems (e.g. GSD)
        self.categories = {}  # per-category breakdown

    def summary_counts(self):
        return {
            "add": len(self.to_add),
            "up_to_date": len(self.up_to_date),
            "conflicts": len(self.conflicts),
            "merge": len(self.to_merge),
            "preserved": len(self.preserved),
        }


def analyze_conflicts(manifest, repo_dir):
    """
    Run conflict analysis comparing manifest items against user's system.
    Returns a ConflictReport.
    """
    report = ConflictReport()

    for cat_name, cat_config in manifest.get("categories", {}).items():
        target = _resolve_path(cat_config.get("target"))
        cat_report = {
            "to_add": [],
            "up_to_date": [],
            "conflicts": [],
            "to_merge": [],
            "preserved": [],
        }

        items = cat_config.get("items", {})

        for item_path, item_meta in items.items():
            entry = {
                "category": cat_name,
                "item_path": item_path,
                "meta": item_meta,
            }

            if target is None:
                # Categories like "mcp" with no direct target
                if cat_config.get("merge_strategy") == "merge_entries":
                    report.to_merge.append(entry)
                    cat_report["to_merge"].append(entry)
                else:
                    report.to_add.append(entry)
                    cat_report["to_add"].append(entry)
                continue

            user_file = os.path.join(target, item_path)
            is_dir = item_meta.get("is_directory", False)

            if is_dir:
                if not os.path.isdir(user_file):
                    report.to_add.append(entry)
                    cat_report["to_add"].append(entry)
                else:
                    user_checksum = compute_dir_checksum(user_file)
                    if user_checksum == item_meta.get("checksum"):
                        report.up_to_date.append(entry)
                        cat_report["up_to_date"].append(entry)
                    else:
                        report.conflicts.append(entry)
                        cat_report["conflicts"].append(entry)
            else:
                if not os.path.isfile(user_file):
                    report.to_add.append(entry)
                    cat_report["to_add"].append(entry)
                else:
                    user_checksum = compute_file_checksum(user_file)
                    if user_checksum == item_meta.get("checksum"):
                        report.up_to_date.append(entry)
                        cat_report["up_to_date"].append(entry)
                    elif item_meta.get("is_registry"):
                        report.to_merge.append(entry)
                        cat_report["to_merge"].append(entry)
                    else:
                        report.conflicts.append(entry)
                        cat_report["conflicts"].append(entry)

        # Find user files NOT in manifest (preserved)
        if target and os.path.isdir(target):
            manifest_items = set(items.keys())
            for item_name in _scan_target_items(target, cat_name):
                if item_name not in manifest_items:
                    cat_report["preserved"].append(item_name)
                    report.preserved.append({
                        "category": cat_name,
                        "item_path": item_name,
                    })

        report.categories[cat_name] = cat_report

    # Detect existing hook systems not in manifest
    report.existing_systems = _detect_existing_systems(manifest)

    return report


def _scan_target_items(target, cat_name):
    """Scan a target directory for items relevant to a category."""
    items = []
    if not os.path.isdir(target):
        return items
    for entry in os.listdir(target):
        if entry.startswith(".") or entry == "archive":
            continue
        full = os.path.join(target, entry)
        if cat_name in ("skills", "credentials"):
            if os.path.isdir(full):
                items.append(entry + "/")
        elif cat_name in ("hooks",):
            if os.path.isfile(full) and entry.endswith(".js"):
                items.append(entry)
        elif cat_name in ("rules",):
            # Rules have subdirs (UserPromptSubmit/, Stop/)
            if os.path.isdir(full) and entry not in ("archive", "backups", "repos"):
                for sub in os.listdir(full):
                    if sub.endswith(".md") and not sub.startswith("."):
                        items.append(os.path.join(entry, sub))
        else:
            # Generic: list files
            if os.path.isfile(full):
                items.append(entry)
    return items


def _detect_existing_systems(manifest):
    """Find hooks in settings.json that aren't part of this manifest."""
    existing = []
    try:
        with open(SETTINGS_JSON, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except (IOError, json.JSONDecodeError):
        return existing

    hooks_config = settings.get("hooks", {})
    manifest_hooks = set()
    hooks_cat = manifest.get("categories", {}).get("hooks", {})
    for item_path in hooks_cat.get("items", {}):
        manifest_hooks.add(item_path)

    for event, groups in hooks_config.items():
        if not isinstance(groups, list):
            continue
        for group in groups:
            for hook in group.get("hooks", []):
                cmd = hook.get("command", "")
                # Extract filename from command
                filename = _extract_hook_filename(cmd)
                if filename and filename not in manifest_hooks:
                    existing.append({
                        "event": event,
                        "filename": filename,
                        "matcher": group.get("matcher", "*"),
                        "command": cmd,
                    })
    return existing


def _extract_hook_filename(command):
    """Extract the hook filename from a settings.json command string."""
    # Typical: node "/path/to/hooks/filename.js"
    # or: node C:/Users/.../hooks/filename.js
    if not command:
        return None
    parts = command.replace('"', "").replace("'", "").split("/")
    if parts:
        last = parts[-1].strip()
        if last.endswith(".js"):
            return last
    return None


# -------------------------------------------------------------------------
# Report formatter
# -------------------------------------------------------------------------


def format_report(manifest, report, owner_repo):
    """Format the conflict report for terminal display."""
    version = manifest.get("version", "unknown")
    lines = []
    lines.append("=" * 60)
    lines.append(f"CONFIG IMPORT: {owner_repo} v{version}")
    lines.append("=" * 60)

    for cat_name, cat_config in manifest.get("categories", {}).items():
        cat_data = report.categories.get(cat_name, {})
        item_count = len(cat_config.get("items", {}))
        lines.append("")
        lines.append(f"--- {cat_name.upper()} ({item_count} items) " + "-" * max(0, 40 - len(cat_name)))

        # Show existing user items (preserved)
        preserved = cat_data.get("preserved", [])
        if preserved:
            lines.append("  YOUR EXISTING:")
            for p in preserved[:10]:
                p_name = p if isinstance(p, str) else p.get("item_path", "?")
                lines.append(f"    [i] {p_name}")
            if len(preserved) > 10:
                lines.append(f"    ... and {len(preserved) - 10} more")

        # Show existing hook systems
        if cat_name == "hooks" and report.existing_systems:
            if not preserved:
                lines.append("  YOUR EXISTING:")
            for sys_hook in report.existing_systems:
                lines.append(f"    [i] {sys_hook['filename']} ({sys_hook['event']})")

        # Show items to add
        to_add = cat_data.get("to_add", [])
        if to_add:
            lines.append("  WILL ADD:")
            for item in to_add:
                item_path = item.get("item_path", "?") if isinstance(item, dict) else str(item)
                desc = ""
                meta = item.get("meta", {}) if isinstance(item, dict) else {}
                if meta.get("description"):
                    desc = f" -- {meta['description']}"
                if meta.get("settings_entry"):
                    se = meta["settings_entry"]
                    desc += f" ({se.get('event', '')})"
                lines.append(f"    [+] {item_path}{desc}")

        # Show up-to-date items
        up_to_date = cat_data.get("up_to_date", [])
        if up_to_date:
            lines.append(f"  UP TO DATE: {len(up_to_date)} items")

        # Show conflicts
        conflicts = cat_data.get("conflicts", [])
        if conflicts:
            lines.append("  CONFLICTS:")
            for item in conflicts:
                item_path = item.get("item_path", "?") if isinstance(item, dict) else str(item)
                lines.append(f"    [!] {item_path} -- you have a customized version")

        # Show merge items
        to_merge = cat_data.get("to_merge", [])
        if to_merge:
            lines.append("  WILL MERGE:")
            for item in to_merge:
                item_path = item.get("item_path", "?") if isinstance(item, dict) else str(item)
                lines.append(f"    [~] {item_path} (entry-level merge)")

        if not to_add and not conflicts and not to_merge and not up_to_date:
            lines.append("  (no items)")

    # Summary
    counts = report.summary_counts()
    lines.append("")
    lines.append("=" * 60)
    lines.append(
        f"SUMMARY: {counts['add']} add, {counts['up_to_date']} up-to-date, "
        f"{counts['conflicts']} conflicts, {len(report.preserved)} preserved"
    )
    if counts["conflicts"] > 0:
        lines.append("Conflicts will be SKIPPED. Review later: config review")
    lines.append(f"Uninstall anytime: config uninstall {owner_repo}")
    lines.append("=" * 60)

    return "\n".join(lines)


# -------------------------------------------------------------------------
# State file management
# -------------------------------------------------------------------------


def _load_json(path, default):
    """Load a JSON file, returning default if missing or invalid."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return default


def _save_json(path, data):
    """Save data as formatted JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_repos():
    return _load_json(CONFIG_REPOS_JSON, [])


def save_repos(repos):
    _save_json(CONFIG_REPOS_JSON, repos)


def load_installed():
    return _load_json(CONFIG_INSTALLED_JSON, {})


def save_installed(installed):
    _save_json(CONFIG_INSTALLED_JSON, installed)


def load_pending():
    return _load_json(CONFIG_PENDING_JSON, [])


def save_pending(pending):
    _save_json(CONFIG_PENDING_JSON, pending)


# -------------------------------------------------------------------------
# Backup management
# -------------------------------------------------------------------------


def create_config_backup(owner_repo, changes=None):
    """
    Create a timestamped backup before config import.
    Returns backup directory path.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    backup_dir = os.path.join(CONFIG_BACKUPS_DIR, ts)
    os.makedirs(backup_dir, exist_ok=True)

    restore_manifest = {
        "timestamp": ts,
        "repo": owner_repo,
        "action": "import",
        "changes": changes or [],
    }

    # Backup settings.json
    if os.path.isfile(SETTINGS_JSON):
        shutil.copy2(SETTINGS_JSON, os.path.join(backup_dir, "settings.json"))

    _save_json(os.path.join(backup_dir, "restore.json"), restore_manifest)
    log.info(f"Backup created: {backup_dir}")
    return backup_dir


def list_config_backups():
    """List all available backup timestamps."""
    if not os.path.isdir(CONFIG_BACKUPS_DIR):
        return []
    backups = sorted(os.listdir(CONFIG_BACKUPS_DIR), reverse=True)
    result = []
    for b in backups:
        restore_path = os.path.join(CONFIG_BACKUPS_DIR, b, "restore.json")
        meta = _load_json(restore_path, {})
        result.append({
            "id": b,
            "path": os.path.join(CONFIG_BACKUPS_DIR, b),
            "repo": meta.get("repo", "unknown"),
            "action": meta.get("action", "unknown"),
            "changes_count": len(meta.get("changes", [])),
        })
    return result


def restore_config_backup(backup_id):
    """Restore from a specific backup."""
    backup_dir = os.path.join(CONFIG_BACKUPS_DIR, backup_id)
    if not os.path.isdir(backup_dir):
        return {"error": f"Backup not found: {backup_id}"}

    restore_path = os.path.join(backup_dir, "restore.json")
    restore_data = _load_json(restore_path, {})
    changes = restore_data.get("changes", [])
    results = {"restored": [], "archived": [], "errors": []}

    # Restore settings.json
    settings_backup = os.path.join(backup_dir, "settings.json")
    if os.path.isfile(settings_backup):
        shutil.copy2(settings_backup, SETTINGS_JSON)
        results["restored"].append(SETTINGS_JSON)

    # Process each change in reverse
    for change in reversed(changes):
        change_type = change.get("type")
        change_path = _resolve_path(change.get("path", ""))
        backup_file = change.get("backup")

        try:
            if change_type == "added" and os.path.exists(change_path):
                # Archive the added file
                archive_dir = os.path.join(CLAUDE_DIR, "archive", "config-restore")
                os.makedirs(archive_dir, exist_ok=True)
                ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                archive_name = os.path.basename(change_path) + f".{ts}"
                shutil.move(change_path, os.path.join(archive_dir, archive_name))
                results["archived"].append(change_path)
            elif change_type == "replaced" and backup_file:
                src = os.path.join(backup_dir, backup_file)
                if os.path.isfile(src):
                    os.makedirs(os.path.dirname(change_path), exist_ok=True)
                    shutil.copy2(src, change_path)
                    results["restored"].append(change_path)
        except Exception as e:
            results["errors"].append(f"{change_path}: {e}")

    return results


# -------------------------------------------------------------------------
# Git/GitHub operations
# -------------------------------------------------------------------------


def _check_gh_cli():
    """Check if gh CLI is available and authenticated."""
    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return False, "gh CLI not found"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "gh CLI not found. Install: https://cli.github.com/"

    # Check auth
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return False, "gh not authenticated. Run: gh auth login"
    except subprocess.TimeoutExpired:
        return False, "gh auth check timed out"

    return True, "ok"


def clone_or_pull_repo(owner_repo):
    """Clone a config repo (or pull if already cloned). Returns clone dir path."""
    clone_dir = _repo_clone_dir(owner_repo)

    if os.path.isdir(os.path.join(clone_dir, ".git")):
        # Already cloned -- pull latest
        log.info(f"Pulling latest from {owner_repo}")
        result = subprocess.run(
            ["git", "-C", clone_dir, "pull", "--ff-only"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            log.warn(f"git pull failed: {result.stderr.strip()}")
            # Non-fatal: use existing checkout
        return clone_dir

    # Fresh clone
    os.makedirs(CONFIG_REPOS_DIR, exist_ok=True)
    log.info(f"Cloning {owner_repo} -> {clone_dir}")
    result = subprocess.run(
        ["gh", "repo", "clone", owner_repo, clone_dir, "--", "--depth=1"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to clone {owner_repo}: {result.stderr.strip()}")
    return clone_dir


# -------------------------------------------------------------------------
# Delegation to per-manager setup/uninstall
# -------------------------------------------------------------------------


# Map manifest category names to sub-manager skill directories that have
# setup.js / uninstall.js scripts. This mapping is intentionally loose --
# categories that don't map to a manager are handled by generic file copy.
CATEGORY_MANAGER_MAP = {
    "hooks": "hook-manager",
    "rules": "rule-manager",
    "skills": None,  # skills are just directory copies, no setup.js needed
    "credentials": "credential-manager",
    "mcp": "mcp-manager",
    "claude-md": None,  # simple file copy
}


def _run_node_script(script_path, args=None):
    """Run a Node.js script and return (success, stdout, stderr)."""
    cmd = ["node", script_path] + (args or [])
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return False, "", str(e)


def install_category(cat_name, cat_config, repo_dir, report_cat, headless=False, headless_safe=False):
    """
    Install items for a single manifest category.
    Delegates to manager setup.js when available, otherwise does direct file copy.
    Returns list of change records for restore.json.
    """
    changes = []
    target = _resolve_path(cat_config.get("target"))
    repo_path = cat_config.get("path", "")
    source_dir = os.path.join(repo_dir, repo_path)
    items = cat_config.get("items", {})
    conflicts_in_cat = set()
    report_conflicts = report_cat.get("conflicts", []) if report_cat else []
    for c in report_conflicts:
        cpath = c.get("item_path", "") if isinstance(c, dict) else str(c)
        conflicts_in_cat.add(cpath)

    for item_path, item_meta in items.items():
        is_conflict = item_path in conflicts_in_cat

        if is_conflict and headless_safe:
            log.info(f"  [SKIP] {cat_name}/{item_path} (conflict, headless-safe)")
            continue
        if is_conflict and not headless:
            log.info(f"  [SKIP] {cat_name}/{item_path} (conflict)")
            continue

        src = os.path.join(source_dir, item_path)
        is_dir = item_meta.get("is_directory", False)

        if target is None:
            # Special categories (e.g. mcp) -- handled by merge logic
            changes.extend(_handle_special_category(cat_name, cat_config, src, item_path, item_meta))
            continue

        dest = os.path.join(target, item_path)

        # Backup existing file before overwriting
        backup_rel = None
        if os.path.exists(dest) and is_conflict:
            backup_rel = os.path.join(cat_name, item_path)

        if is_dir:
            if os.path.isdir(src):
                if os.path.isdir(dest) and is_conflict:
                    # Archive existing
                    archive_dir = os.path.join(CLAUDE_DIR, "archive", cat_name)
                    os.makedirs(archive_dir, exist_ok=True)
                    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                    shutil.move(dest, os.path.join(archive_dir, os.path.basename(dest) + f".{ts}"))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copytree(src, dest, dirs_exist_ok=True)
                change_type = "replaced" if is_conflict else "added"
                changes.append({"type": change_type, "path": dest, "backup": backup_rel})
                log.info(f"  [{'REPLACE' if is_conflict else 'ADD'}] {cat_name}/{item_path}")
        else:
            if os.path.isfile(src):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                existed = os.path.isfile(dest)
                shutil.copy2(src, dest)
                change_type = "replaced" if existed and is_conflict else "added"
                changes.append({"type": change_type, "path": dest, "backup": backup_rel})
                log.info(f"  [{'REPLACE' if existed and is_conflict else 'ADD'}] {cat_name}/{item_path}")

        # Register hooks in settings.json if needed
        if cat_name == "hooks" and item_meta.get("settings_entry"):
            se = item_meta["settings_entry"]
            _register_hook_in_settings(item_path, se)
            changes.append({
                "type": "settings_hook_added",
                "event": se.get("event", ""),
                "filename": item_path,
                "id": item_meta.get("id", item_path),
            })

    return changes


def _register_hook_in_settings(filename, settings_entry):
    """Register a hook in settings.json based on manifest settings_entry."""
    try:
        with open(SETTINGS_JSON, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except (IOError, json.JSONDecodeError):
        settings = {}

    event = settings_entry.get("event", "")
    matcher = settings_entry.get("matcher", "*")
    is_async = settings_entry.get("async", False)

    if not event:
        return

    if "hooks" not in settings:
        settings["hooks"] = {}
    if event not in settings["hooks"]:
        settings["hooks"][event] = []

    hook_path = os.path.join(HOOKS_DIR, filename).replace("\\", "/")
    command = f'node "{hook_path}"'

    # Check if already registered
    for group in settings["hooks"][event]:
        for h in group.get("hooks", []):
            if h.get("command", "").find(filename) != -1:
                return  # already registered

    # Find or create matcher group
    target_group = None
    for group in settings["hooks"][event]:
        if group.get("matcher") == matcher:
            target_group = group
            break
    if target_group is None:
        target_group = {"matcher": matcher, "hooks": []}
        settings["hooks"][event].append(target_group)

    hook_entry = {"type": "command", "command": command}
    if is_async:
        hook_entry["timeout"] = 15000
    target_group["hooks"].append(hook_entry)

    with open(SETTINGS_JSON, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def _handle_special_category(cat_name, cat_config, src, item_path, item_meta):
    """Handle categories with no direct target (e.g. mcp merge)."""
    changes = []
    if cat_name == "mcp" and cat_config.get("merge_strategy") == "merge_entries":
        # MCP: merge server entries from defaults into user's servers.yaml
        # This is informational only for now -- users configure MCP via mcp-manager
        log.info(f"  [INFO] {cat_name}/{item_path} -- sample config available in repo")
    return changes


def uninstall_category(cat_name, cat_config, installed_items):
    """
    Uninstall items for a single category.
    Returns list of actions taken.
    """
    actions = []
    target = _resolve_path(cat_config.get("target"))

    for item_path, item_state in installed_items.items():
        if target is None:
            continue

        dest = os.path.join(target, item_path)
        is_dir = item_state.get("is_directory", False)

        if not os.path.exists(dest):
            continue

        # Archive instead of delete
        archive_dir = os.path.join(CLAUDE_DIR, "archive", f"config-uninstall-{cat_name}")
        os.makedirs(archive_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        archive_name = os.path.basename(dest if not is_dir else dest.rstrip("/")) + f".{ts}"

        try:
            shutil.move(dest, os.path.join(archive_dir, archive_name))
            actions.append({"action": "archived", "path": dest})
            log.info(f"  [ARCHIVE] {cat_name}/{item_path}")
        except Exception as e:
            actions.append({"action": "error", "path": dest, "error": str(e)})
            log.error(f"  [ERROR] {cat_name}/{item_path}: {e}")

    # Remove hooks from settings.json
    if cat_name == "hooks":
        for item_path, item_state in installed_items.items():
            se = item_state.get("settings_entry")
            if se:
                _unregister_hook_from_settings(item_path, se)
                actions.append({"action": "settings_hook_removed", "filename": item_path})

    return actions


def _unregister_hook_from_settings(filename, settings_entry):
    """Remove a hook from settings.json."""
    try:
        with open(SETTINGS_JSON, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except (IOError, json.JSONDecodeError):
        return

    event = settings_entry.get("event", "")
    if not event or "hooks" not in settings or event not in settings["hooks"]:
        return

    modified = False
    for group in settings["hooks"][event]:
        original_len = len(group.get("hooks", []))
        group["hooks"] = [
            h for h in group.get("hooks", [])
            if filename not in h.get("command", "")
        ]
        if len(group["hooks"]) < original_len:
            modified = True

    # Clean up empty groups
    settings["hooks"][event] = [g for g in settings["hooks"][event] if g.get("hooks")]

    if modified:
        with open(SETTINGS_JSON, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)


# -------------------------------------------------------------------------
# Installed state tracking
# -------------------------------------------------------------------------


def record_installed(owner_repo, manifest, changes):
    """Record what was installed from a repo into installed.json."""
    installed = load_installed()
    repo_key = _repo_slug(owner_repo)

    installed[repo_key] = {
        "owner_repo": owner_repo,
        "version": manifest.get("version", "unknown"),
        "updated": manifest.get("updated", ""),
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "categories": {},
    }

    for cat_name, cat_config in manifest.get("categories", {}).items():
        cat_items = {}
        for change in changes:
            if change.get("type") in ("added", "replaced"):
                path_str = change.get("path", "")
                target = _resolve_path(cat_config.get("target", ""))
                if target and path_str.startswith(target):
                    rel = os.path.relpath(path_str, target)
                    item_meta = cat_config.get("items", {}).get(rel, {})
                    cat_items[rel] = {
                        "checksum": item_meta.get("checksum", ""),
                        "is_directory": item_meta.get("is_directory", False),
                        "settings_entry": item_meta.get("settings_entry"),
                    }
            elif change.get("type") == "settings_hook_added":
                if cat_name == "hooks":
                    fn = change.get("filename", "")
                    if fn not in cat_items:
                        cat_items[fn] = {}
                    cat_items[fn]["settings_entry"] = {
                        "event": change.get("event", ""),
                    }

        if cat_items:
            installed[repo_key]["categories"][cat_name] = cat_items

    save_installed(installed)


# -------------------------------------------------------------------------
# Public command functions (called from super_manager.py)
# -------------------------------------------------------------------------


def do_import(owner_repo=None, headless=False, headless_safe=False):
    """
    Import config from a repo (or update all registered repos).
    """
    _ensure_dirs()

    # Determine which repos to import
    if owner_repo:
        repos_to_import = [owner_repo]
    else:
        repos = load_repos()
        if not repos:
            print("No config repos registered. Usage:")
            print("  config import <owner/repo>")
            return
        repos_to_import = [r["owner_repo"] for r in repos]

    # Check gh CLI
    gh_ok, gh_msg = _check_gh_cli()
    if not gh_ok:
        print(f"[ERROR] {gh_msg}")
        return

    for repo in repos_to_import:
        print(f"\nImporting from {repo}...")
        try:
            clone_dir = clone_or_pull_repo(repo)
        except RuntimeError as e:
            print(f"[ERROR] {e}")
            continue

        # Read and validate manifest
        manifest_path = os.path.join(clone_dir, "manifest.json")
        if not os.path.isfile(manifest_path):
            print(f"[ERROR] No manifest.json in {repo}")
            continue

        manifest = parse_manifest(manifest_path)
        errors = validate_manifest(manifest)
        if errors:
            print(f"[ERROR] Invalid manifest.json:")
            for e in errors:
                print(f"  - {e}")
            continue

        # Run conflict analysis
        report = analyze_conflicts(manifest, clone_dir)

        # Display report
        print(format_report(manifest, report, repo))

        # Determine if we can proceed
        counts = report.summary_counts()
        if counts["add"] == 0 and counts["conflicts"] == 0:
            print("\nNothing to install -- everything is up to date.")
            _register_repo(repo)
            continue

        # Approval
        if not headless and not headless_safe:
            if counts["conflicts"] > 0:
                print(f"\n{counts['conflicts']} conflict(s) will be SKIPPED.")
            response = input(f"\nInstall {counts['add']} items? (y/n): ").strip().lower()
            if response != "y":
                print("Cancelled.")
                continue

        # Create backup BEFORE any changes
        backup_dir = create_config_backup(repo)

        # Install each category
        all_changes = []
        for cat_name, cat_config in manifest.get("categories", {}).items():
            cat_report = report.categories.get(cat_name, {})
            cat_changes = install_category(
                cat_name, cat_config, clone_dir,
                cat_report, headless=headless, headless_safe=headless_safe,
            )
            all_changes.extend(cat_changes)

            # Backup conflicting files
            for change in cat_changes:
                if change.get("backup"):
                    src = _resolve_path(change.get("path", ""))
                    if src and os.path.exists(src):
                        backup_file = os.path.join(backup_dir, change["backup"])
                        os.makedirs(os.path.dirname(backup_file), exist_ok=True)
                        shutil.copy2(src, backup_file)

        # Update restore manifest with actual changes
        restore_path = os.path.join(backup_dir, "restore.json")
        restore_data = _load_json(restore_path, {})
        restore_data["changes"] = all_changes
        _save_json(restore_path, restore_data)

        # Record installed state
        record_installed(repo, manifest, all_changes)
        _register_repo(repo)

        # Queue conflicts for review
        if counts["conflicts"] > 0 and not headless:
            pending = load_pending()
            for conflict in report.conflicts:
                pending.append({
                    "repo": repo,
                    "category": conflict.get("category", ""),
                    "item_path": conflict.get("item_path", ""),
                    "reason": "checksum mismatch -- user customized",
                })
            save_pending(pending)

        # Summary
        added = sum(1 for c in all_changes if c.get("type") == "added")
        replaced = sum(1 for c in all_changes if c.get("type") == "replaced")
        hooks_added = sum(1 for c in all_changes if c.get("type") == "settings_hook_added")
        print(f"\nDone: {added} added, {replaced} replaced, {hooks_added} hooks registered")
        print(f"Backup: {backup_dir}")


def _register_repo(owner_repo):
    """Register a repo in repos.json if not already there."""
    repos = load_repos()
    for r in repos:
        if r.get("owner_repo") == owner_repo:
            return  # already registered
    repos.append({
        "owner_repo": owner_repo,
        "alias": owner_repo.split("/")[-1],
        "added_date": datetime.now(timezone.utc).isoformat(),
    })
    save_repos(repos)


def do_export(owner_repo):
    """Export local config to a repo."""
    _ensure_dirs()

    gh_ok, gh_msg = _check_gh_cli()
    if not gh_ok:
        print(f"[ERROR] {gh_msg}")
        return

    clone_dir = _repo_clone_dir(owner_repo)
    if not os.path.isdir(os.path.join(clone_dir, ".git")):
        print(f"[ERROR] Repo not cloned. Run: config import {owner_repo}")
        return

    manifest_path = os.path.join(clone_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        print(f"[ERROR] No manifest.json in {clone_dir}")
        return

    manifest = parse_manifest(manifest_path)
    updated = 0

    for cat_name, cat_config in manifest.get("categories", {}).items():
        target = _resolve_path(cat_config.get("target"))
        if target is None:
            continue

        repo_path = cat_config.get("path", "")
        dest_dir = os.path.join(clone_dir, repo_path)

        for item_path, item_meta in cat_config.get("items", {}).items():
            src = os.path.join(target, item_path)
            dest = os.path.join(dest_dir, item_path)
            is_dir = item_meta.get("is_directory", False)

            if is_dir and os.path.isdir(src):
                if os.path.isdir(dest):
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
                new_checksum = compute_dir_checksum(dest)
                item_meta["checksum"] = new_checksum
                updated += 1
            elif not is_dir and os.path.isfile(src):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src, dest)
                new_checksum = compute_file_checksum(dest)
                item_meta["checksum"] = new_checksum
                updated += 1

    # Update manifest
    manifest["updated"] = datetime.now(timezone.utc).isoformat()
    _save_json(manifest_path, manifest)

    # Commit and push
    subprocess.run(["git", "-C", clone_dir, "add", "."], capture_output=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    subprocess.run(
        ["git", "-C", clone_dir, "commit", "-m", f"config export {ts}: {updated} items updated"],
        capture_output=True,
    )
    result = subprocess.run(
        ["git", "-C", clone_dir, "push"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"Exported {updated} items to {owner_repo}")
    else:
        print(f"Push failed: {result.stderr.strip()}")
        print(f"Changes committed locally in {clone_dir}")


def do_uninstall(owner_repo=None, uninstall_all=False):
    """Uninstall config items from a repo (or all repos)."""
    installed = load_installed()

    if uninstall_all:
        repos_to_uninstall = list(installed.keys())
    elif owner_repo:
        slug = _repo_slug(owner_repo)
        if slug not in installed:
            print(f"No installed items from {owner_repo}")
            return
        repos_to_uninstall = [slug]
    else:
        print("Usage: config uninstall <owner/repo> or config uninstall --all")
        return

    for slug in repos_to_uninstall:
        repo_state = installed.get(slug, {})
        repo_name = repo_state.get("owner_repo", slug)
        print(f"\nUninstalling items from {repo_name}...")

        # Read manifest from cached clone
        clone_dir = _repo_clone_dir(repo_name)
        manifest_path = os.path.join(clone_dir, "manifest.json")
        manifest = _load_json(manifest_path, {"categories": {}})

        for cat_name, cat_items in repo_state.get("categories", {}).items():
            cat_config = manifest.get("categories", {}).get(cat_name, {
                "target": None,
                "path": cat_name + "/",
            })
            actions = uninstall_category(cat_name, cat_config, cat_items)
            for a in actions:
                if a["action"] == "error":
                    print(f"  [ERROR] {a.get('path', '')}: {a.get('error', '')}")

        del installed[slug]
        save_installed(installed)
        print(f"Uninstalled items from {repo_name}")

    # Clean up pending conflicts for uninstalled repos
    if uninstall_all:
        save_pending([])


def do_add_repo(owner_repo):
    """Register a config repo without importing."""
    _register_repo(owner_repo)
    print(f"Registered config repo: {owner_repo}")


def do_remove_repo(owner_repo):
    """Unregister a config repo (archive clone, don't delete)."""
    repos = load_repos()
    repos = [r for r in repos if r.get("owner_repo") != owner_repo]
    save_repos(repos)

    # Archive the clone
    clone_dir = _repo_clone_dir(owner_repo)
    if os.path.isdir(clone_dir):
        archive_dir = os.path.join(CLAUDE_DIR, "archive", "config-repos")
        os.makedirs(archive_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        shutil.move(clone_dir, os.path.join(archive_dir, _repo_slug(owner_repo) + f".{ts}"))

    print(f"Removed config repo: {owner_repo}")


def do_repos():
    """List registered config repos."""
    repos = load_repos()
    if not repos:
        print("No config repos registered.")
        print(f"Default: config import {DEFAULT_CONFIG_REPO}")
        return

    print("\nRegistered Config Repos:")
    print("-" * 50)
    for r in repos:
        print(f"  {r['owner_repo']}  (added: {r.get('added_date', '?')[:10]})")
    print()


def do_review():
    """Review pending conflicts."""
    pending = load_pending()
    if not pending:
        print("No pending conflicts.")
        return

    print(f"\nPending Conflicts ({len(pending)}):")
    print("-" * 50)
    for i, p in enumerate(pending):
        print(f"  [{i + 1}] {p['repo']} / {p['category']} / {p['item_path']}")
        print(f"      Reason: {p['reason']}")
    print()
    print("Options:")
    print("  config import --headless     Accept all (archive originals)")
    print("  config import --headless-safe  Skip all conflicts")
    print("  Manual: copy the version you want from the repo clone")


def do_status():
    """Show config sync status."""
    installed = load_installed()
    repos = load_repos()
    pending = load_pending()

    print("\nConfig Sync Status")
    print("=" * 50)

    if not installed and not repos:
        print("  No config repos configured.")
        print(f"  Get started: config import {DEFAULT_CONFIG_REPO}")
        print()
        return

    print(f"  Repos: {len(repos)}")
    for r in repos:
        slug = _repo_slug(r["owner_repo"])
        state = installed.get(slug, {})
        version = state.get("version", "not installed")
        cat_count = len(state.get("categories", {}))
        total_items = sum(
            len(items) for items in state.get("categories", {}).values()
        )
        print(f"    {r['owner_repo']}: v{version} ({total_items} items in {cat_count} categories)")

    if pending:
        print(f"\n  Pending conflicts: {len(pending)}")
        print("    Run: config review")

    backups = list_config_backups()
    if backups:
        print(f"\n  Backups: {len(backups)} available")
        latest = backups[0]
        print(f"    Latest: {latest['id']} ({latest['repo']})")

    print()


def do_restore(backup_id=None, list_backups=False):
    """Restore from a backup."""
    if list_backups:
        backups = list_config_backups()
        if not backups:
            print("No backups available.")
            return
        print("\nAvailable Backups:")
        print("-" * 50)
        for b in backups:
            print(f"  {b['id']}  repo={b['repo']}  action={b['action']}  changes={b['changes_count']}")
        return

    if not backup_id:
        print("Usage: config restore <backup-id> or config restore --list")
        return

    print(f"Restoring from backup {backup_id}...")
    result = restore_config_backup(backup_id)

    if "error" in result:
        print(f"[ERROR] {result['error']}")
        return

    print(f"  Restored: {len(result.get('restored', []))} files")
    print(f"  Archived: {len(result.get('archived', []))} files")
    if result.get("errors"):
        for e in result["errors"]:
            print(f"  [ERROR] {e}")


# -------------------------------------------------------------------------
# Verification (smoke tests for doctor integration)
# -------------------------------------------------------------------------


def verify_config_state():
    """
    Verify installed config state matches reality.
    Returns dict with healthy/issues lists (doctor-compatible).
    """
    healthy = []
    issues = []
    installed = load_installed()

    for slug, repo_state in installed.items():
        for cat_name, cat_items in repo_state.get("categories", {}).items():
            for item_path, item_state in cat_items.items():
                target = None
                # Resolve target from well-known categories
                if cat_name == "hooks":
                    target = HOOKS_DIR
                elif cat_name == "rules":
                    target = RULES_DIR
                elif cat_name == "skills":
                    target = GLOBAL_SKILLS_DIR
                elif cat_name == "credentials":
                    target = os.path.join(GLOBAL_SKILLS_DIR, "credential-manager")
                elif cat_name == "claude-md":
                    target = CLAUDE_DIR

                if target is None:
                    continue

                full_path = os.path.join(target, item_path)
                if os.path.exists(full_path):
                    healthy.append(f"{cat_name}/{item_path}")
                else:
                    issues.append({
                        "item": f"{cat_name}/{item_path}",
                        "problem": f"Installed from {slug} but file missing at {full_path}",
                    })

    return {"healthy": healthy, "issues": issues}


# -------------------------------------------------------------------------
# Entry point for standalone testing
# -------------------------------------------------------------------------

if __name__ == "__main__":
    # Simple standalone test
    if len(sys.argv) < 2:
        print("config_sync.py - Config import/export orchestrator")
        print("Run via: python super_manager.py config <action>")
        sys.exit(0)

    action = sys.argv[1]
    rest = sys.argv[2:]

    if action == "import":
        repo = rest[0] if rest and not rest[0].startswith("-") else None
        headless = "--headless" in rest
        headless_safe = "--headless-safe" in rest
        do_import(repo, headless=headless, headless_safe=headless_safe)
    elif action == "export":
        if not rest:
            print("Usage: config export <owner/repo>")
            sys.exit(1)
        do_export(rest[0])
    elif action == "uninstall":
        if "--all" in rest:
            do_uninstall(uninstall_all=True)
        elif rest:
            do_uninstall(rest[0])
        else:
            print("Usage: config uninstall <owner/repo> or --all")
    elif action == "add-repo":
        if not rest:
            print("Usage: config add-repo <owner/repo>")
            sys.exit(1)
        do_add_repo(rest[0])
    elif action == "remove-repo":
        if not rest:
            print("Usage: config remove-repo <owner/repo>")
            sys.exit(1)
        do_remove_repo(rest[0])
    elif action == "repos":
        do_repos()
    elif action == "review":
        do_review()
    elif action == "status":
        do_status()
    elif action == "restore":
        list_mode = "--list" in rest
        backup_id = next((r for r in rest if not r.startswith("-")), None)
        do_restore(backup_id=backup_id, list_backups=list_mode)
    else:
        print(f"Unknown config action: {action}")
