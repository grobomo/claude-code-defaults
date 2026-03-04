"""
smoke_settings.py - Verify settings.json integrity.

Checks:
  - settings.json is valid JSON
  - No duplicate hook entries (same filename registered twice for same event)
  - No orphaned hooks (command points to a file that doesn't exist)

Returns: {"healthy": [...], "issues": [{item, problem}]}
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.configuration_paths import SETTINGS_JSON


def _load_json(path, default=None):
    """Load a JSON file, returning default on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return default


def _extract_file_path_from_command(command):
    """
    Extract the script file path from a hook command string.
    Returns (filename, full_path) or (None, None) if unparseable.

    Handles patterns like:
      node "~/.claude/hooks/tool-reminder.js"
      TRIGGER=SessionEnd bash "$HOME/.claude/skills/.../backup.sh"
    """
    if not command:
        return None, None

    # Remove env var assignments at start (e.g. TRIGGER=SessionEnd)
    parts = command.split()
    cmd_parts = []
    for part in parts:
        if "=" in part and not part.startswith('"') and not part.startswith("/") and not part.startswith("$"):
            continue  # skip env var
        cmd_parts.append(part)

    # The remaining parts should be: runner "path" or runner path
    # Find the path-like argument
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE", "")

    for part in cmd_parts:
        cleaned = part.strip('"').strip("'")
        # Expand $HOME
        cleaned = cleaned.replace("$HOME", home)
        # Expand %USERPROFILE%
        cleaned = os.path.expandvars(cleaned)

        # Check if it looks like a file path
        if cleaned.endswith(".js") or cleaned.endswith(".sh") or cleaned.endswith(".py"):
            filename = os.path.basename(cleaned)
            return filename, cleaned

    return None, None


def run():
    """Verify settings.json structure and hook integrity."""
    healthy = []
    issues = []

    # Check 1: File exists and is valid JSON
    if not os.path.isfile(SETTINGS_JSON):
        return {
            "healthy": [],
            "issues": [{"item": "settings.json", "problem": "File not found (system may not be set up yet)"}],
        }

    settings = _load_json(SETTINGS_JSON)
    if settings is None:
        return {
            "healthy": [],
            "issues": [{"item": "settings.json", "problem": "File exists but is not valid JSON"}],
        }

    healthy.append("settings.json is valid JSON")

    # Check hooks section
    hooks_config = settings.get("hooks", {})
    if not hooks_config:
        healthy.append("No hooks configured in settings.json")
        return {"healthy": healthy, "issues": issues}

    # Check 2: No duplicate hook entries per event
    for event, groups in hooks_config.items():
        if not isinstance(groups, list):
            issues.append({
                "item": f"hooks.{event}",
                "problem": f"Expected list of groups, got {type(groups).__name__}",
            })
            continue

        # Collect all filenames across all groups for this event
        seen_filenames = {}
        for group_idx, group in enumerate(groups):
            if not isinstance(group, dict):
                issues.append({
                    "item": f"hooks.{event}[{group_idx}]",
                    "problem": "Group is not a dict",
                })
                continue

            hooks_list = group.get("hooks", [])
            if not isinstance(hooks_list, list):
                continue

            for hook in hooks_list:
                command = hook.get("command", "")
                filename, full_path = _extract_file_path_from_command(command)

                if not filename:
                    # Empty hooks array entries or unparseable commands
                    if command:
                        issues.append({
                            "item": f"hooks.{event}",
                            "problem": f"Cannot parse file from command: {command[:80]}",
                        })
                    continue

                # Check for duplicates within same event
                if filename in seen_filenames:
                    issues.append({
                        "item": f"hooks.{event}/{filename}",
                        "problem": f"Duplicate: '{filename}' registered twice in {event} (groups {seen_filenames[filename]} and {group_idx})",
                    })
                else:
                    seen_filenames[filename] = group_idx

                # Check 3: File exists on disk
                if full_path and not os.path.isfile(full_path):
                    issues.append({
                        "item": f"hooks.{event}/{filename}",
                        "problem": f"Orphaned hook: file not found at {full_path}",
                    })
                elif full_path:
                    healthy.append(f"hooks.{event}/{filename} (file exists)")

        # Check for empty groups (groups with no hooks)
        for group_idx, group in enumerate(groups):
            if isinstance(group, dict):
                hooks_list = group.get("hooks", [])
                if isinstance(hooks_list, list) and len(hooks_list) == 0:
                    matcher = group.get("matcher", "*")
                    issues.append({
                        "item": f"hooks.{event}[{group_idx}]",
                        "problem": f"Empty hooks array for matcher '{matcher}' (dead group)",
                    })

    return {"healthy": healthy, "issues": issues}


if __name__ == "__main__":
    result = run()
    print(f"Healthy: {len(result['healthy'])}")
    for h in result["healthy"]:
        print(f"  [OK] {h}")
    if result["issues"]:
        print(f"\nIssues: {len(result['issues'])}")
        for issue in result["issues"]:
            print(f"  [!] {issue['item']}: {issue['problem']}")
    else:
        print("\nNo issues found.")
