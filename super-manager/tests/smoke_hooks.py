"""
smoke_hooks.py - Verify all registered hooks match real system state.

Checks:
  - Each hook in hook-registry.json has a corresponding file in ~/.claude/hooks/
  - Each managed hook has a matching entry in settings.json
  - No ghost entries (registry points to missing files)

Returns: {"healthy": [...], "issues": [{item, problem}]}
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.configuration_paths import HOOKS_DIR, HOOK_REGISTRY, SETTINGS_JSON


def _load_json(path, default=None):
    """Load a JSON file, returning default on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return default


def _extract_filenames_from_settings(settings):
    """Extract all hook filenames referenced in settings.json hooks config."""
    filenames = set()
    hooks_config = settings.get("hooks", {})
    for event, groups in hooks_config.items():
        if not isinstance(groups, list):
            continue
        for group in groups:
            for hook in group.get("hooks", []):
                cmd = hook.get("command", "")
                if not cmd:
                    continue
                # Extract filename from command like: node "C:/Users/.../hooks/filename.js"
                # or: TRIGGER=SessionEnd bash "$HOME/.claude/skills/.../backup.sh"
                parts = cmd.replace('"', "").replace("'", "").replace("\\", "/").split("/")
                for part in reversed(parts):
                    part = part.strip()
                    if part.endswith(".js") or part.endswith(".sh"):
                        filenames.add(part)
                        break
    return filenames


def run():
    """Verify hook-registry entries against disk and settings.json."""
    healthy = []
    issues = []

    # Load registry
    registry = _load_json(HOOK_REGISTRY)
    if registry is None:
        # Registry doesn't exist yet -- not an error if system not set up
        if not os.path.isfile(HOOK_REGISTRY):
            return {"healthy": [], "issues": [{"item": "hook-registry.json", "problem": "File not found (system may not be set up yet)"}]}
        return {"healthy": [], "issues": [{"item": "hook-registry.json", "problem": "Invalid JSON"}]}

    hooks = registry.get("hooks", [])
    if not hooks:
        return {"healthy": ["hook-registry.json (empty, no hooks to check)"], "issues": []}

    # Load settings.json
    settings = _load_json(SETTINGS_JSON, {})
    settings_filenames = _extract_filenames_from_settings(settings)

    for hook in hooks:
        name = hook.get("name", "unknown")
        event = hook.get("event", "")
        command = hook.get("command", "")
        managed = hook.get("managed", False)

        # Skip unmanaged/disabled hooks (empty event = disabled in registry)
        if not event and not managed:
            healthy.append(f"{name} (disabled/unmanaged, skipped)")
            continue

        # For managed hooks with a command, check file exists
        if managed and command:
            # Extract file path from command
            # Typical: node "~/.claude/hooks/tool-reminder.js"
            # or: TRIGGER=SessionEnd bash "$HOME/.claude/skills/.../backup.sh"
            hook_file = None

            # Try to find the hooks/ directory file reference
            cmd_clean = command.replace('"', "").replace("'", "")
            if "/.claude/hooks/" in cmd_clean.replace("\\", "/"):
                # Extract filename after hooks/
                idx = cmd_clean.replace("\\", "/").rfind("/.claude/hooks/")
                rest = cmd_clean.replace("\\", "/")[idx + len("/.claude/hooks/"):]
                filename = rest.split()[0] if rest else ""
                if filename:
                    hook_file = os.path.join(HOOKS_DIR, filename)
            elif ".claude/skills/" in cmd_clean.replace("\\", "/"):
                # Hook lives in a skill directory (e.g. backup.sh)
                # Just check if the full resolved path exists
                # Extract the path portion
                for token in cmd_clean.split():
                    expanded = os.path.expandvars(token.replace("$HOME", os.environ.get("HOME", os.environ.get("USERPROFILE", ""))))
                    if os.path.isfile(expanded):
                        hook_file = expanded
                        break

            if hook_file:
                if os.path.isfile(hook_file):
                    healthy.append(f"{name} (file exists: {os.path.basename(hook_file)})")
                else:
                    issues.append({
                        "item": name,
                        "problem": f"Hook file not found on disk: {hook_file}",
                    })
            else:
                # Could not parse file path from command
                issues.append({
                    "item": name,
                    "problem": f"Could not extract file path from command: {command}",
                })

            # Check settings.json has a matching entry
            # Extract just the filename
            filename_only = os.path.basename(hook_file) if hook_file else ""
            if filename_only and filename_only not in settings_filenames:
                issues.append({
                    "item": name,
                    "problem": f"Hook '{filename_only}' in registry but not found in settings.json hooks",
                })
            elif filename_only:
                healthy.append(f"{name} (settings.json entry matches)")

        elif managed and not command:
            # Managed but no command -- registry entry is incomplete
            issues.append({
                "item": name,
                "problem": "Managed hook has no command in registry",
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
