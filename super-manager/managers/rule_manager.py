"""
rule_manager.py - Manage rule .md files with YAML frontmatter.

Rules live in ~/.claude/rules/ organized by hook event:
  ~/.claude/rules/UserPromptSubmit/  # Injected when prompt keywords match
  ~/.claude/rules/Stop/              # Checked against Claude's response

Supports:
  - CRUD: list, add, remove, enable, disable, get, match, verify
  - Local snapshots: backup, restore, list_backups
  - Git repos: add_repo, remove_repo, list_repos, backup_to_repo, restore_from_repo
  - Auto hooks: set_auto_backup (SessionEnd), set_auto_restore (SessionStart)
"""
import sys
import os
import glob
import json
import shutil
import datetime
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.configuration_paths import (
    RULES_BASE, RULES_BACKUP_DIR,
    RULES_REPOS_DIR, RULES_REPOS_CONFIG,
    HOOKS_DIR, VALID_HOOK_EVENTS,
)
from shared.logger import create_logger
from shared.config_file_handler import read_frontmatter, write_frontmatter, read_json, write_json
from shared.file_operations import archive_file, ensure_directory

log = create_logger("rule-manager")

# Hook events that have rule subdirectories
RULE_EVENTS = ["UserPromptSubmit", "Stop"]

# Default repos config
_DEFAULT_CONFIG = {
    "repos": [],
    "auto_restore_on_start": False,
    "auto_backup_on_end": False,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _event_dir(event):
    """Get the directory for a hook event."""
    return os.path.join(RULES_BASE, event)


def _rule_path(rule_id, event="UserPromptSubmit"):
    """Build the full file path for a rule ID in a given event dir."""
    return os.path.join(_event_dir(event), rule_id + ".md")


def _find_rule(rule_id):
    """Find which event dir contains this rule. Returns (event, path) or (None, None)."""
    for event in RULE_EVENTS:
        fpath = _rule_path(rule_id, event)
        if os.path.exists(fpath):
            return event, fpath
    return None, None


def _scan_event(event):
    """Scan one event directory for .md files with frontmatter."""
    event_dir = _event_dir(event)
    ensure_directory(event_dir)
    results = []
    for md_file in sorted(glob.glob(os.path.join(event_dir, "*.md"))):
        meta = read_frontmatter(md_file)
        if meta is None:
            log.warn("Skipping file with no frontmatter: " + md_file)
            continue
        meta["_file_path"] = md_file
        meta["_event"] = event
        results.append((md_file, meta))
    return results


def _scan_all():
    """Scan all event directories. Returns list of (file_path, metadata_dict) tuples."""
    results = []
    for event in RULE_EVENTS:
        results.extend(_scan_event(event))
    return results


def _normalize_bool(value):
    """Normalize a frontmatter boolean value to Python bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def _sanitize_keywords(keywords):
    """
    Enforce single-word keywords. Multi-word phrases and hyphenated words
    get split into individual words, deduped. Never use multi-word keywords --
    use regex patterns instead for phrase matching.
    "reload mcp" -> ["reload", "mcp"]
    "long-running" -> ["long", "running"]
    """
    if not isinstance(keywords, list):
        keywords = [keywords]
    singles = set()
    for kw in keywords:
        # Split on spaces and hyphens
        parts = str(kw).replace("-", " ").split()
        for part in parts:
            part = part.strip().lower()
            if part:
                singles.add(part)
    return sorted(singles)


def _load_repos_config():
    """Load repos.json, return config dict."""
    if not os.path.exists(RULES_REPOS_CONFIG):
        return dict(_DEFAULT_CONFIG)
    data = read_json(RULES_REPOS_CONFIG, default=dict(_DEFAULT_CONFIG))
    for key in _DEFAULT_CONFIG:
        if key not in data:
            data[key] = _DEFAULT_CONFIG[key]
    return data


def _save_repos_config(config):
    """Save repos.json."""
    ensure_directory(os.path.dirname(RULES_REPOS_CONFIG))
    write_json(RULES_REPOS_CONFIG, config)


def _git(*args, cwd=None):
    """Run a git command, return (success, stdout, stderr)."""
    try:
        r = subprocess.run(
            ["git"] + list(args),
            cwd=cwd, capture_output=True, text=True, timeout=30
        )
        return r.returncode == 0, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return False, "", str(e)


def _repo_local_path(name):
    """Local clone path for a named repo."""
    return os.path.join(RULES_REPOS_DIR, name)


# ---------------------------------------------------------------------------
# Public API - CRUD
# ---------------------------------------------------------------------------

def list_all():
    """List all rules across all event directories."""
    entries = _scan_all()
    items = []
    enabled_count = 0
    disabled_count = 0

    for file_path, meta in entries:
        is_enabled = _normalize_bool(meta.get("enabled", False))
        body = meta.get("body", "")

        if is_enabled:
            enabled_count += 1
        else:
            disabled_count += 1

        items.append({
            "id": meta.get("id", os.path.splitext(os.path.basename(file_path))[0]),
            "name": meta.get("name", ""),
            "keywords": meta.get("keywords", []),
            "enabled": is_enabled,
            "priority": int(meta.get("priority", 50)),
            "event": meta.get("_event", "UserPromptSubmit"),
            "file_path": file_path,
            "has_content": len(body.strip()) > 10,
        })

    total = len(items)
    summary = (
        str(total) + " rules, "
        + str(enabled_count) + " enabled, "
        + str(disabled_count) + " disabled"
    )
    log.info("list_all: " + summary)
    return {"items": items, "summary": summary}


def add_item(rule_id, name, keywords, content, priority=10, event="UserPromptSubmit"):
    """Create a new rule .md file with frontmatter."""
    event_dir = _event_dir(event)
    ensure_directory(event_dir)
    file_path = _rule_path(rule_id, event)

    if os.path.exists(file_path):
        log.warn("add_item: rule already exists: " + rule_id)
        return {
            "success": False,
            "error": "Rule " + repr(rule_id) + " already exists",
        }

    meta = {
        "id": rule_id,
        "name": name,
        "keywords": _sanitize_keywords(keywords),
        "enabled": "true",
        "priority": str(priority),
    }
    write_frontmatter(file_path, meta, content)
    log.info("add_item: created " + repr(rule_id) + " in " + event)
    return {"success": True, "id": rule_id, "event": event, "file_path": file_path}


def remove_item(rule_id):
    """Archive a rule (never delete)."""
    event, file_path = _find_rule(rule_id)
    if event is None:
        log.warn("remove_item: not found: " + rule_id)
        return {"success": False, "error": "Rule " + repr(rule_id) + " not found"}

    archive_path = archive_file(file_path, reason="removed")
    log.info("remove_item: archived " + repr(rule_id) + " -> " + str(archive_path))
    return {"success": True, "id": rule_id, "archived_to": archive_path}


def enable_item(rule_id):
    """Set enabled: true in frontmatter."""
    event, file_path = _find_rule(rule_id)
    if event is None:
        return {"success": False, "error": "Rule " + repr(rule_id) + " not found"}

    meta = read_frontmatter(file_path)
    if meta is None:
        return {"success": False, "error": "Invalid frontmatter in " + repr(rule_id)}

    body = meta.pop("body", "")
    meta["enabled"] = "true"
    write_frontmatter(file_path, meta, body)
    log.info("enable_item: enabled " + repr(rule_id))
    return {"success": True, "id": rule_id, "enabled": True}


def disable_item(rule_id):
    """Set enabled: false in frontmatter."""
    event, file_path = _find_rule(rule_id)
    if event is None:
        return {"success": False, "error": "Rule " + repr(rule_id) + " not found"}

    meta = read_frontmatter(file_path)
    if meta is None:
        return {"success": False, "error": "Invalid frontmatter in " + repr(rule_id)}

    body = meta.pop("body", "")
    meta["enabled"] = "false"
    write_frontmatter(file_path, meta, body)
    log.info("disable_item: disabled " + repr(rule_id))
    return {"success": True, "id": rule_id, "enabled": False}


def get_item(rule_id):
    """Return full rule content + metadata."""
    event, file_path = _find_rule(rule_id)
    if event is None:
        return {"success": False, "error": "Rule " + repr(rule_id) + " not found"}

    meta = read_frontmatter(file_path)
    if meta is None:
        return {"success": False, "error": "Invalid frontmatter in " + repr(rule_id)}

    body = meta.get("body", "")
    return {
        "success": True,
        "id": meta.get("id", rule_id),
        "name": meta.get("name", ""),
        "keywords": meta.get("keywords", []),
        "enabled": _normalize_bool(meta.get("enabled", False)),
        "priority": int(meta.get("priority", 50)),
        "event": event,
        "file_path": file_path,
        "has_content": len(body.strip()) > 10,
        "content": body,
    }


def get_matching_rules(prompt_text):
    """Find all enabled rules whose keywords match the prompt text."""
    prompt_lower = prompt_text.lower()
    entries = _scan_all()
    matches = []

    for file_path, meta in entries:
        if not _normalize_bool(meta.get("enabled", False)):
            continue

        keywords = meta.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = [keywords]

        matched_keywords = [kw for kw in keywords if kw.lower() in prompt_lower]
        if not matched_keywords:
            continue

        body = meta.get("body", "")
        priority = int(meta.get("priority", 50))
        matches.append({
            "id": meta.get("id", os.path.splitext(os.path.basename(file_path))[0]),
            "name": meta.get("name", ""),
            "priority": priority,
            "event": meta.get("_event", "UserPromptSubmit"),
            "matched_keywords": matched_keywords,
            "content": body,
        })

    matches.sort(key=lambda m: m["priority"])
    log.info("get_matching_rules: " + str(len(matches)) + " matches")
    return matches


def verify_all():
    """Health check - validate all rule files across all event dirs."""
    healthy = []
    issues = []
    seen_ids = {}
    # Base fields required for all rules
    base_fields = ["id", "name", "enabled"]
    # Stop rules use 'pattern' (regex); UserPromptSubmit uses 'keywords'

    for event in RULE_EVENTS:
        event_dir = _event_dir(event)
        ensure_directory(event_dir)
        for md_file in sorted(glob.glob(os.path.join(event_dir, "*.md"))):
            basename = os.path.basename(md_file)
            label = event + "/" + basename
            meta = read_frontmatter(md_file)

            if meta is None:
                issues.append({"item": label, "problem": "No valid YAML frontmatter"})
                continue

            missing = [f for f in base_fields if f not in meta or meta[f] == ""]
            # Stop rules need 'pattern' OR 'keywords'; UserPromptSubmit needs 'keywords'
            if event == "Stop":
                if not meta.get("pattern") and not meta.get("keywords"):
                    missing.append("pattern")
            else:
                if not meta.get("keywords"):
                    missing.append("keywords")
            if missing:
                issues.append({"item": label, "problem": "Missing fields: " + ", ".join(missing)})
                continue

            inst_id = meta.get("id", "")
            if inst_id in seen_ids:
                issues.append({
                    "item": label,
                    "problem": "Duplicate ID " + repr(inst_id) + " (also in " + seen_ids[inst_id] + ")",
                })
                continue

            seen_ids[inst_id] = label
            healthy.append({"id": inst_id, "name": meta.get("name", ""), "event": event, "file": basename})

    log.info("verify_all: " + str(len(healthy)) + " healthy, " + str(len(issues)) + " issues")
    return {"healthy": healthy, "issues": issues}


# ---------------------------------------------------------------------------
# Local export / import (directory-based, used by backup and repo functions)
# ---------------------------------------------------------------------------

def export_rules(dest_dir):
    """
    Export all rules to a directory, organized by hook event.
    Creates: dest_dir/UserPromptSubmit/*.md, dest_dir/Stop/*.md
    """
    exported = []
    for event in RULE_EVENTS:
        src_dir = _event_dir(event)
        if not os.path.exists(src_dir):
            continue
        dst_event = os.path.join(dest_dir, event)
        os.makedirs(dst_event, exist_ok=True)
        for md_file in glob.glob(os.path.join(src_dir, "*.md")):
            basename = os.path.basename(md_file)
            shutil.copy2(md_file, os.path.join(dst_event, basename))
            exported.append(event + "/" + basename)

    log.info("export_rules: " + str(len(exported)) + " files -> " + dest_dir)
    return {"success": True, "exported": exported, "dest_dir": dest_dir}


def import_rules(src_dir, overwrite=False):
    """
    Import rules from a directory organized by hook event.
    Expects: src_dir/UserPromptSubmit/*.md, src_dir/Stop/*.md
    Skips existing files unless overwrite=True.
    """
    imported = []
    skipped = []
    errors = []

    for event in RULE_EVENTS:
        src_event = os.path.join(src_dir, event)
        if not os.path.isdir(src_event):
            continue
        dst_event = _event_dir(event)
        ensure_directory(dst_event)

        for md_file in glob.glob(os.path.join(src_event, "*.md")):
            basename = os.path.basename(md_file)
            dst_path = os.path.join(dst_event, basename)

            if os.path.exists(dst_path) and not overwrite:
                skipped.append(event + "/" + basename)
                continue

            if os.path.exists(dst_path) and overwrite:
                archive_file(dst_path, reason="import-overwrite")

            try:
                shutil.copy2(md_file, dst_path)
                imported.append(event + "/" + basename)
            except Exception as e:
                errors.append(event + "/" + basename + ": " + str(e))

    log.info("import_rules: " + str(len(imported)) + " imported, " + str(len(skipped)) + " skipped")
    return {"success": True, "imported": imported, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Local backup / restore (snapshots)
# ---------------------------------------------------------------------------

def backup_rules(name=None):
    """Snapshot all current rules to ~/.claude/rules/backups/<name>/"""
    if name is None:
        name = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    backup_dir = os.path.join(RULES_BACKUP_DIR, name)
    if os.path.exists(backup_dir):
        return {"success": False, "error": "Backup " + repr(name) + " already exists"}

    result = export_rules(backup_dir)
    log.info("backup_rules: " + name + " (" + str(len(result["exported"])) + " files)")
    return {"success": True, "name": name, "path": backup_dir, "files": result["exported"]}


def restore_rules(name):
    """Restore from a named local backup. Auto-backs up current state first."""
    backup_dir = os.path.join(RULES_BACKUP_DIR, name)
    if not os.path.isdir(backup_dir):
        return {"success": False, "error": "Backup " + repr(name) + " not found"}

    pre_restore = backup_rules("pre-restore-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    result = import_rules(backup_dir, overwrite=True)
    log.info("restore_rules: restored from " + name)
    return {
        "success": True,
        "restored_from": name,
        "pre_restore_backup": pre_restore.get("name", ""),
        "imported": result["imported"],
    }


def list_backups():
    """List all available local rule backups."""
    if not os.path.isdir(RULES_BACKUP_DIR):
        return {"backups": []}

    backups = []
    for entry in sorted(os.listdir(RULES_BACKUP_DIR)):
        backup_path = os.path.join(RULES_BACKUP_DIR, entry)
        if not os.path.isdir(backup_path):
            continue
        file_count = 0
        for event in RULE_EVENTS:
            event_dir = os.path.join(backup_path, event)
            if os.path.isdir(event_dir):
                file_count += len(glob.glob(os.path.join(event_dir, "*.md")))
        backups.append({"name": entry, "path": backup_path, "file_count": file_count})

    return {"backups": backups}


# ---------------------------------------------------------------------------
# Git repo management
# ---------------------------------------------------------------------------

def add_repo(url, name=None):
    """Register a git repo as a backup/restore target."""
    if name is None:
        # Derive name from URL: "grobomo/claude-rules" -> "claude-rules"
        name = url.rstrip("/").split("/")[-1].replace(".git", "")

    config = _load_repos_config()
    for repo in config["repos"]:
        if repo["name"] == name:
            return {"success": False, "error": "Repo " + repr(name) + " already registered"}

    config["repos"].append({"name": name, "url": url, "enabled": True})
    _save_repos_config(config)
    log.info("add_repo: registered " + repr(name) + " -> " + url)
    return {"success": True, "name": name, "url": url}


def remove_repo(name):
    """Unregister a git repo."""
    config = _load_repos_config()
    original_len = len(config["repos"])
    config["repos"] = [r for r in config["repos"] if r["name"] != name]
    if len(config["repos"]) == original_len:
        return {"success": False, "error": "Repo " + repr(name) + " not found"}

    _save_repos_config(config)
    log.info("remove_repo: unregistered " + repr(name))
    return {"success": True, "name": name}


def list_repos():
    """List all registered git repos."""
    config = _load_repos_config()
    return {
        "repos": config["repos"],
        "auto_restore_on_start": config.get("auto_restore_on_start", False),
        "auto_backup_on_end": config.get("auto_backup_on_end", False),
    }


def backup_to_repo(name):
    """
    Export rules to a git repo, commit, and push.
    Clones repo if not cached locally, pulls if cached.
    """
    config = _load_repos_config()
    repo = next((r for r in config["repos"] if r["name"] == name), None)
    if repo is None:
        return {"success": False, "error": "Repo " + repr(name) + " not registered"}

    ensure_directory(RULES_REPOS_DIR)
    local = _repo_local_path(name)
    url = repo["url"]

    # Clone or pull
    if os.path.isdir(os.path.join(local, ".git")):
        ok, out, err = _git("pull", "--ff-only", cwd=local)
        if not ok:
            log.warn("backup_to_repo: pull failed for " + name + ": " + err)
    else:
        ok, out, err = _git("clone", url, local)
        if not ok:
            return {"success": False, "error": "Clone failed: " + err}

    # Export rules into the repo
    result = export_rules(local)

    # Commit and push
    _git("add", "-A", cwd=local)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ok, out, err = _git("commit", "-m", "rule backup " + timestamp, cwd=local)
    if not ok and "nothing to commit" in err + out:
        log.info("backup_to_repo: no changes to commit for " + name)
        return {"success": True, "name": name, "exported": result["exported"], "pushed": False}

    ok, out, err = _git("push", cwd=local)
    if not ok:
        return {"success": False, "error": "Push failed: " + err, "exported": result["exported"]}

    log.info("backup_to_repo: pushed " + str(len(result["exported"])) + " files to " + name)
    return {"success": True, "name": name, "exported": result["exported"], "pushed": True}


def restore_from_repo(name, overwrite=False):
    """
    Pull from a git repo and import rules.
    Clones repo if not cached locally, pulls if cached.
    Skips existing files unless overwrite=True.
    """
    config = _load_repos_config()
    repo = next((r for r in config["repos"] if r["name"] == name), None)
    if repo is None:
        return {"success": False, "error": "Repo " + repr(name) + " not registered"}

    ensure_directory(RULES_REPOS_DIR)
    local = _repo_local_path(name)
    url = repo["url"]

    # Clone or pull
    if os.path.isdir(os.path.join(local, ".git")):
        ok, out, err = _git("pull", "--ff-only", cwd=local)
        if not ok:
            log.warn("restore_from_repo: pull failed for " + name + ": " + err)
    else:
        ok, out, err = _git("clone", url, local)
        if not ok:
            return {"success": False, "error": "Clone failed: " + err}

    # Import from the repo
    result = import_rules(local, overwrite=overwrite)
    log.info("restore_from_repo: " + str(len(result["imported"])) + " imported from " + name)
    return {
        "success": True,
        "name": name,
        "imported": result["imported"],
        "skipped": result["skipped"],
        "errors": result["errors"],
    }


# ---------------------------------------------------------------------------
# Auto-backup / auto-restore hooks
# ---------------------------------------------------------------------------

_AUTO_RESTORE_HOOK = "rule-auto-restore.js"
_AUTO_BACKUP_HOOK = "rule-auto-backup.js"


def _hook_path(filename):
    return os.path.join(HOOKS_DIR, filename)


def _write_auto_restore_hook():
    """Write SessionStart hook that restores from all enabled repos."""
    content = '''#!/usr/bin/env node
/**
 * @hook rule-auto-restore
 * @event SessionStart
 * @description Auto-restore rules from git repos on session start
 */
const { execSync } = require("child_process");
const path = require("path");
const os = require("os");

try {
  const mgr = path.join(os.homedir(), ".claude", "super-manager");
  execSync(
    'python -c "' +
    "import sys; sys.path.insert(0, '" + mgr.replace(/\\\\/g, "/") + "'); " +
    "from managers.rule_manager import list_repos, restore_from_repo; " +
    "cfg = list_repos(); " +
    "[restore_from_repo(r['name']) for r in cfg['repos'] if r.get('enabled')]" +
    '"',
    { timeout: 30000, stdio: "pipe" }
  );
} catch {}
console.log("{}");
'''
    with open(_hook_path(_AUTO_RESTORE_HOOK), "w", encoding="utf-8") as f:
        f.write(content)


def _write_auto_backup_hook():
    """Write SessionEnd hook that backs up to all enabled repos."""
    content = '''#!/usr/bin/env node
/**
 * @hook rule-auto-backup
 * @event SessionEnd
 * @description Auto-backup rules to git repos on session end
 */
const { execSync } = require("child_process");
const path = require("path");
const os = require("os");

try {
  const mgr = path.join(os.homedir(), ".claude", "super-manager");
  execSync(
    'python -c "' +
    "import sys; sys.path.insert(0, '" + mgr.replace(/\\\\/g, "/") + "'); " +
    "from managers.rule_manager import list_repos, backup_to_repo; " +
    "cfg = list_repos(); " +
    "[backup_to_repo(r['name']) for r in cfg['repos'] if r.get('enabled')]" +
    '"',
    { timeout: 30000, stdio: "pipe" }
  );
} catch {}
console.log("{}");
'''
    with open(_hook_path(_AUTO_BACKUP_HOOK), "w", encoding="utf-8") as f:
        f.write(content)


def set_auto_restore(enabled):
    """
    Toggle auto-restore on session start.
    When enabled, creates a SessionStart hook that pulls from all enabled repos.
    Requires hook-manager to register the hook in settings.json.
    """
    config = _load_repos_config()
    config["auto_restore_on_start"] = enabled
    _save_repos_config(config)

    hook_file = _hook_path(_AUTO_RESTORE_HOOK)
    if enabled:
        _write_auto_restore_hook()
        # Use hook-manager to register in settings.json
        _register_hook(_AUTO_RESTORE_HOOK, "SessionStart")
        log.info("set_auto_restore: enabled")
    else:
        if os.path.exists(hook_file):
            archive_file(hook_file, reason="disabled")
        _unregister_hook(_AUTO_RESTORE_HOOK, "SessionStart")
        log.info("set_auto_restore: disabled")

    return {"success": True, "auto_restore_on_start": enabled}


def set_auto_backup(enabled):
    """
    Toggle auto-backup on session end.
    When enabled, creates a SessionEnd hook that pushes to all enabled repos.
    Requires hook-manager to register the hook in settings.json.
    """
    config = _load_repos_config()
    config["auto_backup_on_end"] = enabled
    _save_repos_config(config)

    hook_file = _hook_path(_AUTO_BACKUP_HOOK)
    if enabled:
        _write_auto_backup_hook()
        _register_hook(_AUTO_BACKUP_HOOK, "SessionEnd")
        log.info("set_auto_backup: enabled")
    else:
        if os.path.exists(hook_file):
            archive_file(hook_file, reason="disabled")
        _unregister_hook(_AUTO_BACKUP_HOOK, "SessionEnd")
        log.info("set_auto_backup: disabled")

    return {"success": True, "auto_backup_on_end": enabled}


def _register_hook(filename, event):
    """Register a hook in settings.json + registry via hook-manager."""
    try:
        from managers.hook_manager import add_item as hm_add
        command = 'node "' + _hook_path(filename) + '"'
        hm_add(name=filename.replace(".js", ""), event=event, command=command,
               description="Auto-managed by rule-manager")
    except ImportError:
        log.warn("hook-manager not available -- install it to register hooks in settings.json")


def _unregister_hook(filename, event):
    """Unregister a hook from settings.json + registry via hook-manager."""
    try:
        from managers.hook_manager import remove_item as hm_remove
        hm_remove(name=filename.replace(".js", ""))
    except ImportError:
        log.warn("hook-manager not available -- install it to unregister hooks from settings.json")
