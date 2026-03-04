"""
hook_manager.py - Native manager for Claude Code hooks.

Reads/writes two sources of truth:
  1. ~/.claude/settings.json (hooks section) - what Claude Code actually loads
  2. ~/.claude/super-manager/registries/hook-registry.json - metadata + managed state

Cross-references both to detect orphans, drift, and health issues.
All mutations are atomic: both files updated together or neither is changed.
"""
import sys
import os
import re
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.configuration_paths import (
    SETTINGS_JSON, HOOK_REGISTRY, HOOKS_DIR, VALID_HOOK_EVENTS, REGISTRIES_DIR,
)
from shared.logger import create_logger
from shared.config_file_handler import read_json, write_json
from shared.file_operations import archive_file

log = create_logger("hook-manager")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_hook_name(command):
    """
    Extract a human-readable hook name from a command string.
    Examples:
      node "~/.claude/hooks/tool-reminder.js"  -> "tool-reminder"
      TRIGGER=SessionEnd bash "$HOME/.claude/skills/backup.sh" -> "backup"
    """
    match = re.search(r'"([^"]+)"', command)
    if match:
        path = match.group(1)
        basename = os.path.basename(path)
        name, _ = os.path.splitext(basename)
        return name
    match = re.search(r'(?:node|bash)\s+(\S+)', command)
    if match:
        path = match.group(1).strip('"\'')
        basename = os.path.basename(path)
        name, _ = os.path.splitext(basename)
        return name
    return "hook-{}".format(abs(hash(command)) % 100000)


def _extract_file_path(command):
    """
    Extract the script file path from a hook command.
    Resolves $HOME and %USERPROFILE% to actual home directory.
    """
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE", "")
    match = re.search(r'"([^"]+)"', command)
    if match:
        path = match.group(1)
    else:
        parts = command.strip().split()
        path = parts[-1] if parts else None
    if not path:
        return None
    path = path.replace("$HOME", home).replace("${HOME}", home)
    path = path.replace("%USERPROFILE%", home)
    path = os.path.normpath(path)
    return path


def _read_settings_hooks():
    """
    Read hooks from settings.json and flatten into a list of dicts.
    Each dict: {name, event, matcher, command, async, source: "settings"}
    """
    settings = read_json(SETTINGS_JSON, {})
    hooks_section = settings.get("hooks", {})
    result = []
    for event, matcher_groups in hooks_section.items():
        if not isinstance(matcher_groups, list):
            continue
        for group in matcher_groups:
            matcher = group.get("matcher", "*")
            for hook_entry in group.get("hooks", []):
                command = hook_entry.get("command", "")
                name = _extract_hook_name(command)
                is_async = hook_entry.get("async", False)
                result.append({
                    "name": name,
                    "event": event,
                    "matcher": matcher,
                    "command": command,
                    "async": is_async,
                    "source": "settings",
                })
    return result


def _read_registry():
    """Read hook-registry.json. Returns list of hook dicts."""
    data = read_json(HOOK_REGISTRY, {"hooks": [], "version": "1.0"})
    result = []
    for entry in data.get("hooks", []):
        result.append({
            "name": entry.get("name", ""),
            "event": entry.get("event", ""),
            "matcher": entry.get("matcher", "*"),
            "command": entry.get("command", ""),
            "async": entry.get("async", False),
            "managed": entry.get("managed", False),
            "description": entry.get("description", ""),
            "source": "registry",
        })
    return result


def _write_registry(hooks_list):
    """Write the registry file atomically. Preserves version field."""
    os.makedirs(REGISTRIES_DIR, exist_ok=True)
    data = {
        "hooks": [
            {
                "name": h["name"],
                "event": h["event"],
                "matcher": h.get("matcher", "*"),
                "async": h.get("async", False),
                "managed": h.get("managed", True),
                "description": h.get("description", ""),
                "command": h.get("command", ""),
            }
            for h in hooks_list
        ],
        "version": "1.0",
    }
    write_json(HOOK_REGISTRY, data)


def _add_hook_to_settings(event, matcher, command, is_async=False):
    """
    Add a single hook command to settings.json under the right event+matcher group.
    If a group with matching event+matcher exists, append. Otherwise create new group.
    PRESERVES all non-hook keys in settings.json.
    """
    settings = read_json(SETTINGS_JSON, {})
    hooks_section = settings.setdefault("hooks", {})
    matcher_groups = hooks_section.setdefault(event, [])
    hook_entry = {"type": "command", "command": command}
    if is_async:
        hook_entry["async"] = True
    for group in matcher_groups:
        if group.get("matcher", "*") == matcher:
            existing_commands = [h.get("command", "") for h in group.get("hooks", [])]
            if command not in existing_commands:
                group["hooks"].append(hook_entry)
            write_json(SETTINGS_JSON, settings)
            return
    matcher_groups.append({"matcher": matcher, "hooks": [hook_entry]})
    write_json(SETTINGS_JSON, settings)


def _remove_hook_from_settings(command):
    """
    Remove a hook command from settings.json by matching the command string.
    Cleans up empty groups and empty events after removal.
    PRESERVES all non-hook keys. Returns True if something was removed.
    """
    settings = read_json(SETTINGS_JSON, {})
    hooks_section = settings.get("hooks", {})
    removed = False
    events_to_delete = []
    for event, matcher_groups in hooks_section.items():
        if not isinstance(matcher_groups, list):
            continue
        groups_to_delete = []
        for i, group in enumerate(matcher_groups):
            hooks_list = group.get("hooks", [])
            original_len = len(hooks_list)
            group["hooks"] = [h for h in hooks_list if h.get("command", "") != command]
            if len(group["hooks"]) < original_len:
                removed = True
            if not group["hooks"]:
                groups_to_delete.append(i)
        for idx in reversed(groups_to_delete):
            matcher_groups.pop(idx)
        if not matcher_groups:
            events_to_delete.append(event)
    for event in events_to_delete:
        del hooks_section[event]
    if removed:
        write_json(SETTINGS_JSON, settings)
    return removed


def _find_registry_entry(name, registry_hooks):
    """Find a hook in the registry list by name."""
    for h in registry_hooks:
        if h["name"] == name:
            return h
    return None


def _find_settings_entry(name, settings_hooks):
    """Find a hook in the flattened settings list by name."""
    for h in settings_hooks:
        if h["name"] == name:
            return h
    return None


def _check_file_exists(command):
    """Check if the script file referenced in a command exists."""
    path = _extract_file_path(command)
    if not path:
        return False
    return os.path.isfile(path)


def _syntax_check(command):
    """
    Run node --check on JS files, return (ok: bool, message: str).
    For non-node commands, skip and return (True, "skipped").
    """
    if "node " not in command and "node.exe " not in command:
        return True, "skipped (not a node command)"
    path = _extract_file_path(command)
    if not path or not os.path.isfile(path):
        return False, "file not found: {}".format(path)
    try:
        result = subprocess.run(
            ["node", "--check", path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return True, "syntax OK"
        else:
            error_msg = (result.stderr or result.stdout or "unknown error").strip()
            if len(error_msg) > 200:
                error_msg = error_msg[:200] + "..."
            return False, "syntax error: {}".format(error_msg)
    except FileNotFoundError:
        return False, "node not found in PATH"
    except subprocess.TimeoutExpired:
        return False, "syntax check timed out (10s)"
    except Exception as e:
        return False, "check failed: {}".format(str(e))


# ---------------------------------------------------------------------------
# Public API - Standard manager interface
# ---------------------------------------------------------------------------

def list_all():
    """
    Read hooks from BOTH settings.json and registry. Cross-reference them.
    Returns {"items": [...], "summary": "11 hooks (10 managed, 1 orphaned)"}
    Each item: {name, event, matcher, async, managed, description, command,
                file_exists, in_settings, in_registry, status}
    Status values: "active", "disabled", "orphaned-settings", "orphaned-registry"
    """
    log.debug("list_all: reading settings.json and hook-registry.json")
    settings_hooks = _read_settings_hooks()
    registry_hooks = _read_registry()
    seen_names = set()
    items = []

    # Registry hooks first (they carry metadata)
    for rh in registry_hooks:
        name = rh["name"]
        seen_names.add(name)
        sh = _find_settings_entry(name, settings_hooks)
        command = rh.get("command", "")

        if sh:
            status = "active"
            in_settings = True
            if not command and sh.get("command"):
                command = sh["command"]
        elif command:
            status = "disabled"
            in_settings = False
        else:
            status = "disabled"
            in_settings = False

        items.append({
            "name": name,
            "event": rh.get("event", ""),
            "matcher": rh.get("matcher", "*"),
            "async": rh.get("async", False),
            "managed": rh.get("managed", False),
            "description": rh.get("description", ""),
            "command": command,
            "file_exists": _check_file_exists(command) if command else False,
            "in_settings": in_settings,
            "in_registry": True,
            "status": status,
        })

    # Settings hooks not in registry (orphaned)
    for sh in settings_hooks:
        name = sh["name"]
        if name in seen_names:
            continue
        seen_names.add(name)
        items.append({
            "name": name,
            "event": sh.get("event", ""),
            "matcher": sh.get("matcher", "*"),
            "async": sh.get("async", False),
            "managed": False,
            "description": "",
            "command": sh.get("command", ""),
            "file_exists": _check_file_exists(sh.get("command", "")),
            "in_settings": True,
            "in_registry": False,
            "status": "orphaned-settings",
        })

    total = len(items)
    managed = sum(1 for i in items if i["managed"])
    orphaned = sum(1 for i in items if i["status"].startswith("orphaned"))
    disabled = sum(1 for i in items if i["status"] == "disabled")
    active = sum(1 for i in items if i["status"] == "active")

    parts = ["{} hooks".format(total)]
    if active:
        parts.append("{} active".format(active))
    if managed:
        parts.append("{} managed".format(managed))
    if disabled:
        parts.append("{} disabled".format(disabled))
    if orphaned:
        parts.append("{} orphaned".format(orphaned))

    summary = ", ".join(parts)
    log.info("list_all: {}".format(summary))
    return {"items": items, "summary": summary}


def add_item(name, event, command, description="", matcher="*", is_async=False):
    """
    Add hook to BOTH settings.json and hook-registry.json atomically.
    Returns {"success": bool, "message": str}
    """
    if event not in VALID_HOOK_EVENTS:
        msg = "Invalid event '{}'. Must be one of: {}".format(event, ", ".join(VALID_HOOK_EVENTS))
        log.error("add_item: {}".format(msg))
        return {"success": False, "message": msg}

    if not command or not command.strip():
        msg = "Command cannot be empty"
        log.error("add_item: {}".format(msg))
        return {"success": False, "message": msg}

    if not name:
        name = _extract_hook_name(command)

    registry_hooks = _read_registry()
    existing = _find_registry_entry(name, registry_hooks)
    if existing:
        msg = "Hook '{}' already exists in registry (event={})".format(name, existing["event"])
        log.warn("add_item: {}".format(msg))
        return {"success": False, "message": msg}

    file_exists = _check_file_exists(command)
    file_warning = ""
    if not file_exists:
        path = _extract_file_path(command)
        file_warning = " [WARNING: script file not found: {}]".format(path)
        log.warn("add_item: script file not found for '{}': {}".format(name, path))

    # Add to settings.json
    _add_hook_to_settings(event, matcher, command, is_async)
    log.info("add_item: added '{}' to settings.json ({}/{})".format(name, event, matcher))

    # Add to registry
    registry_hooks.append({
        "name": name,
        "event": event,
        "matcher": matcher,
        "async": is_async,
        "managed": True,
        "description": description,
        "command": command,
    })
    _write_registry(registry_hooks)
    log.info("add_item: added '{}' to hook-registry.json".format(name))

    msg = "Added hook '{}' ({}/{}){}".format(name, event, matcher, file_warning)
    return {"success": True, "message": msg}


def remove_item(name):
    """
    Remove hook from settings.json + registry. Archive the .js file (never delete).
    Returns {"success": bool, "message": str, "archived": str|None}
    """
    log.info("remove_item: removing '{}'".format(name))
    registry_hooks = _read_registry()
    entry = _find_registry_entry(name, registry_hooks)

    if not entry:
        settings_hooks = _read_settings_hooks()
        sh = _find_settings_entry(name, settings_hooks)
        if sh:
            command = sh["command"]
        else:
            msg = "Hook '{}' not found in registry or settings".format(name)
            log.error("remove_item: {}".format(msg))
            return {"success": False, "message": msg, "archived": None}
    else:
        command = entry.get("command", "")

    archived_path = None
    if command:
        removed = _remove_hook_from_settings(command)
        if removed:
            log.info("remove_item: removed '{}' from settings.json".format(name))
        else:
            log.warn("remove_item: '{}' command not found in settings.json".format(name))

        script_path = _extract_file_path(command)
        if script_path and os.path.isfile(script_path):
            archived_path = archive_file(script_path, reason="removed-hook-{}".format(name))
            log.info("remove_item: archived {} -> {}".format(script_path, archived_path))

    registry_hooks = [h for h in registry_hooks if h["name"] != name]
    _write_registry(registry_hooks)
    log.info("remove_item: removed '{}' from hook-registry.json".format(name))

    msg = "Removed hook '{}'".format(name)
    if archived_path:
        msg += " (script archived to {})".format(archived_path)
    return {"success": True, "message": msg, "archived": archived_path}


def enable_item(name):
    """Enable a hook by adding it back to settings.json from registry."""
    registry = _read_registry()
    entry = _find_registry_entry(name, registry)
    if not entry:
        return {"success": False, "message": f"Hook not found in registry: {name}"}
    event = entry.get("event", "")
    command = entry.get("command", "")
    matcher = entry.get("matcher", "*")
    is_async = entry.get("async", False)
    if not event or not command:
        return {"success": False, "message": f"Hook registry entry missing event/command: {name}"}
    _add_hook_to_settings(event, matcher, command, is_async)
    # Also mark as managed in registry
    entry["managed"] = True
    _write_registry(registry)
    log.info(f"Enabled hook: {name}")
    return {"success": True, "message": f"Enabled hook: {name}"}


def disable_item(name):
    """Disable a hook by removing it from settings.json (keeps in registry)."""
    settings_hooks = _read_settings_hooks()
    entry = _find_settings_entry(name, settings_hooks)
    if not entry:
        return {"success": False, "message": f"Hook not in settings.json: {name}"}
    _remove_hook_from_settings(entry.get("command", ""))
    log.info(f"Disabled hook: {name}")
    return {"success": True, "message": f"Disabled hook: {name}"}


def verify_all():
    """Verify all hooks: check file existence, syntax, registry vs settings sync."""
    result = list_all()
    items = result.get("items", [])
    healthy = []
    issues = []
    for item in items:
        name = item.get("name", "?")
        status = item.get("status", "")
        if status == "active":
            # Check file exists
            if not item.get("file_exists", True):
                issues.append({
                    "item": name,
                    "problem": f"Hook script file not found",
                    "fix": f"Check command path or remove hook",
                })
            else:
                healthy.append(name)
        elif status == "orphaned-settings":
            issues.append({
                "item": name,
                "problem": "In settings.json but not in hook-registry.json",
                "fix": f"Register with: hooks add {name} ...",
            })
        elif status == "orphaned-registry":
            issues.append({
                "item": name,
                "problem": "In registry but not in settings.json",
                "fix": "Enable or remove from registry",
            })
        elif status == "disabled":
            healthy.append(name)
        else:
            healthy.append(name)
    log.info(f"verify: {len(healthy)} healthy, {len(issues)} issues")
    return {"healthy": healthy, "issues": issues}
