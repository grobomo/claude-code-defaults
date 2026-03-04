"""
discover.py - Discovery and auto-registration for super-manager.

Scans ~/.claude/ for existing hooks, skills, MCP servers, and rules.
Everything discovered is automatically registered into the appropriate registry.
No interactive prompts - discovery always auto-registers.

Status terminology:
  MANAGED    = actively used (in settings.json for hooks, enabled in registry
               for skills, enabled in servers.yaml for MCP)
  REGISTERED = documented/tracked in registry but not actively managed
  ORPHANED   = in registry but file doesn't exist on disk
  NO FRONTMATTER = rule .md without proper frontmatter

Usage:
    python -m commands.discover            # discover and auto-register all
    python -m commands.discover --report   # scan only, no changes
"""
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.configuration_paths import (
    HOOKS_DIR, SETTINGS_JSON, GLOBAL_SKILLS_DIR, RULES_DIR,
    HOOK_REGISTRY, SKILL_REGISTRY, REGISTRIES_DIR,
    find_servers_yaml,
)
from shared.config_file_handler import (
    read_json, write_json, read_yaml_servers, read_frontmatter,
)
from shared.file_operations import ensure_directory
from shared.logger import create_logger

log = create_logger("discover")

# Script file extensions we care about (skip .json, .log, .md, .state, .hash, etc)
SCRIPT_EXTENSIONS = {".js", ".sh", ".py", ".ps1", ".bat", ".cmd"}


# ---------------------------------------------------------------------------
# Scanning functions
# ---------------------------------------------------------------------------

def _extract_hook_name(command):
    """Extract hook name from a settings.json command string."""
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
    return None


def _scan_settings_hooks():
    """
    Parse settings.json to build a map of hook_name -> {event, matcher, command, async}.
    Returns dict keyed by hook name.
    """
    settings = read_json(SETTINGS_JSON, {})
    hooks_section = settings.get("hooks", {})
    result = {}

    for event, matcher_groups in hooks_section.items():
        if not isinstance(matcher_groups, list):
            continue
        for group in matcher_groups:
            matcher = group.get("matcher", "*")
            for hook_entry in group.get("hooks", []):
                command = hook_entry.get("command", "")
                name = _extract_hook_name(command)
                if not name:
                    continue
                result[name] = {
                    "event": event,
                    "matcher": matcher,
                    "command": command,
                    "async": hook_entry.get("async", False),
                }

    return result


def _scan_disk_hooks():
    """
    Scan ~/.claude/hooks/ for script files (.js, .sh, .py, etc).
    Returns dict: {script_name_without_ext: full_path}
    """
    result = {}
    if not os.path.isdir(HOOKS_DIR):
        return result

    for entry in os.listdir(HOOKS_DIR):
        full_path = os.path.join(HOOKS_DIR, entry)
        if not os.path.isfile(full_path):
            continue
        _, ext = os.path.splitext(entry)
        if ext.lower() not in SCRIPT_EXTENSIONS:
            continue
        name = os.path.splitext(entry)[0]
        result[name] = full_path

    return result


def _read_hook_registry():
    """Read hook-registry.json and return dict keyed by hook name."""
    data = read_json(HOOK_REGISTRY, {"hooks": []})
    result = {}
    for entry in data.get("hooks", []):
        name = entry.get("name", "")
        if name:
            result[name] = entry
    return result


def _scan_disk_skills():
    """
    Scan ~/.claude/skills/ for directories containing SKILL.md.
    Returns dict: {dir_name: skill_md_path}
    """
    result = {}
    if not os.path.isdir(GLOBAL_SKILLS_DIR):
        return result

    for entry in os.listdir(GLOBAL_SKILLS_DIR):
        skill_dir = os.path.join(GLOBAL_SKILLS_DIR, entry)
        if not os.path.isdir(skill_dir):
            continue
        skill_md = os.path.join(skill_dir, "SKILL.md")
        if os.path.isfile(skill_md):
            result[entry] = skill_md

    return result


def _read_skill_registry():
    """Read skill-registry.json and return dict keyed by skill id."""
    data = read_json(SKILL_REGISTRY, {"skills": []})
    result = {}
    for entry in data.get("skills", []):
        skill_id = entry.get("id", "")
        if skill_id:
            result[skill_id] = entry
    return result


def _scan_rules():
    """
    Scan rule .md files with frontmatter across event subdirectories.
    Returns dict: {rule_id: {meta...}}
    """
    result = {}
    if not os.path.isdir(RULES_DIR):
        return result

    for event_name in os.listdir(RULES_DIR):
        event_dir = os.path.join(RULES_DIR, event_name)
        if not os.path.isdir(event_dir) or event_name == "backups":
            continue

        for entry in os.listdir(event_dir):
            if not entry.endswith(".md"):
                continue
            full_path = os.path.join(event_dir, entry)
            if not os.path.isfile(full_path):
                continue
            meta = read_frontmatter(full_path)
            if meta is None:
                inst_id = os.path.splitext(entry)[0]
                result[inst_id] = {
                    "id": inst_id,
                    "file": entry,
                    "event": event_name,
                    "path": full_path,
                    "has_frontmatter": False,
                    "has_keywords": False,
                    "enabled": False,
                }
                continue

            inst_id = meta.get("id", os.path.splitext(entry)[0])
            keywords = meta.get("keywords", [])
            result[inst_id] = {
                "id": inst_id,
                "name": meta.get("name", ""),
                "file": entry,
                "event": event_name,
                "path": full_path,
                "has_frontmatter": True,
                "has_keywords": bool(keywords),
                "keywords": keywords,
                "enabled": str(meta.get("enabled", "false")).lower() == "true",
            }

    return result


# ---------------------------------------------------------------------------
# Discovery logic
# ---------------------------------------------------------------------------

def discover_hooks():
    """
    Cross-reference disk hooks, settings.json hooks, and registry hooks.
    Returns list of dicts with status for each hook found.

    Status values:
      managed    = in settings.json (actively running)
      registered = NOT in settings.json (tracked, not active)
      orphaned   = in registry but file doesn't exist on disk
    """
    disk_hooks = _scan_disk_hooks()
    settings_hooks = _scan_settings_hooks()
    registry_hooks = _read_hook_registry()

    all_names = set()
    all_names.update(disk_hooks.keys())
    all_names.update(settings_hooks.keys())
    all_names.update(registry_hooks.keys())

    results = []
    for name in sorted(all_names):
        on_disk = name in disk_hooks
        in_settings = name in settings_hooks
        in_registry = name in registry_hooks

        # Determine event from best available source
        event = ""
        if in_settings:
            event = settings_hooks[name].get("event", "")
        elif in_registry:
            event = registry_hooks[name].get("event", "")

        if in_registry and not on_disk:
            # File gone from disk - orphaned
            results.append({
                "name": name,
                "status": "orphaned",
                "event": event,
                "on_disk": False,
                "in_settings": in_settings,
                "in_registry": True,
            })
        elif in_settings:
            # In settings.json = managed (actively running)
            results.append({
                "name": name,
                "status": "managed",
                "event": event,
                "matcher": settings_hooks[name].get("matcher", "*"),
                "command": settings_hooks[name].get("command", ""),
                "async": settings_hooks[name].get("async", False),
                "on_disk": on_disk,
                "in_settings": True,
                "in_registry": in_registry,
            })
        else:
            # On disk or in registry but not in settings = registered (tracked, not active)
            results.append({
                "name": name,
                "status": "registered",
                "event": event,
                "on_disk": on_disk,
                "in_settings": False,
                "in_registry": in_registry,
                "file": disk_hooks.get(name, ""),
            })

    return results


def discover_skills():
    """
    Cross-reference disk skills with registry.
    Returns list of dicts with status for each skill found.

    Status values:
      managed    = in registry AND enabled=true
      registered = in registry but enabled=false (tracked, not active)
      orphaned   = in registry but SKILL.md doesn't exist on disk
      new        = on disk but not yet in registry (will be auto-registered)
    """
    disk_skills = _scan_disk_skills()
    registry_skills = _read_skill_registry()

    all_ids = set()
    all_ids.update(disk_skills.keys())
    all_ids.update(registry_skills.keys())

    results = []
    for skill_id in sorted(all_ids):
        on_disk = skill_id in disk_skills
        in_registry = skill_id in registry_skills

        if in_registry:
            reg = registry_skills[skill_id]
            # Also check if the registered path still exists
            skill_path = reg.get("skillPath", "")
            path_exists = os.path.isfile(skill_path) if skill_path else False
            actually_on_disk = on_disk or path_exists
            enabled = reg.get("enabled", False)

            if not actually_on_disk:
                status = "orphaned"
            elif enabled:
                status = "managed"
            else:
                status = "registered"

            results.append({
                "id": skill_id,
                "name": reg.get("name", skill_id),
                "status": status,
                "on_disk": actually_on_disk,
                "in_registry": True,
                "enabled": enabled,
            })
        else:
            # On disk but not in registry - will be auto-registered
            results.append({
                "id": skill_id,
                "name": skill_id,
                "status": "new",
                "on_disk": True,
                "in_registry": False,
                "skill_path": disk_skills[skill_id],
            })

    return results


def discover_mcp_servers():
    """
    Read servers.yaml and report all servers with managed/registered status.
    MCP servers are always registered (servers.yaml IS the registry).

    Status values:
      managed    = in servers.yaml AND enabled=true
      registered = in servers.yaml but enabled=false
    """
    yaml_path = find_servers_yaml()
    if not yaml_path:
        return [], None

    servers = read_yaml_servers(yaml_path)
    results = []
    for name, config in sorted(servers.items()):
        enabled = config.get("enabled", False)
        results.append({
            "name": name,
            "status": "managed" if enabled else "registered",
            "enabled": enabled,
            "description": config.get("description", ""),
        })

    return results, yaml_path


def discover_rules():
    """
    Scan rule .md files and check frontmatter completeness.
    Returns list of dicts with status for each rule found.

    Status values:
      managed        = has frontmatter with id + keywords + enabled=true
      registered     = has frontmatter but missing keywords or enabled=false
      no_frontmatter = .md file without proper frontmatter
    """
    rules = _scan_rules()
    results = []

    for inst_id, meta in sorted(rules.items()):
        if not meta.get("has_frontmatter"):
            results.append({
                "id": inst_id,
                "file": meta.get("file", ""),
                "status": "no_frontmatter",
            })
        elif meta.get("has_keywords") and meta.get("enabled"):
            results.append({
                "id": inst_id,
                "name": meta.get("name", ""),
                "status": "managed",
                "enabled": True,
            })
        else:
            # Has frontmatter but missing keywords or not enabled
            results.append({
                "id": inst_id,
                "name": meta.get("name", ""),
                "file": meta.get("file", ""),
                "status": "registered",
                "enabled": meta.get("enabled", False),
                "has_keywords": meta.get("has_keywords", False),
            })

    return results


# ---------------------------------------------------------------------------
# Registration functions
# ---------------------------------------------------------------------------

def register_hook(name, event, command, matcher="*", is_async=False, description=""):
    """
    Add a hook to hook-registry.json (does NOT modify settings.json).
    Sets managed=false by default since being in the registry = registered.
    A hook is only managed if it is also in settings.json.
    """
    ensure_directory(REGISTRIES_DIR)
    data = read_json(HOOK_REGISTRY, {"hooks": [], "version": "1.0"})
    hooks_list = data.get("hooks", [])

    # Check for duplicates
    for h in hooks_list:
        if h.get("name") == name:
            log.warn("register_hook: {} already in registry".format(name))
            return False

    hooks_list.append({
        "name": name,
        "event": event,
        "matcher": matcher,
        "async": is_async,
        "managed": False,
        "description": description,
        "command": command,
    })
    data["hooks"] = hooks_list
    write_json(HOOK_REGISTRY, data)
    log.info("register_hook: added {} ({})".format(name, event))
    return True


def register_skill(skill_id, skill_path):
    """
    Add a skill to skill-registry.json.
    Sets enabled=false by default for newly discovered skills.
    """
    ensure_directory(REGISTRIES_DIR)
    data = read_json(SKILL_REGISTRY, {"skills": []})
    skills_list = data.get("skills", [])

    # Check for duplicates
    for s in skills_list:
        if s.get("id") == skill_id:
            log.warn("register_skill: {} already in registry".format(skill_id))
            return False

    skills_list.append({
        "id": skill_id,
        "name": skill_id,
        "keywords": [skill_id.replace("-", " "), skill_id],
        "skillPath": skill_path.replace("\\", "/"),
        "enabled": False,
    })
    data["skills"] = skills_list
    write_json(SKILL_REGISTRY, data)
    log.info("register_skill: added {} ({})".format(skill_id, skill_path))
    return True


def _sync_hook_managed_flags(settings_hooks):
    """
    Update managed flag in hook-registry.json to reflect settings.json state.
    managed=true if hook name is in settings.json, managed=false otherwise.
    """
    data = read_json(HOOK_REGISTRY, {"hooks": [], "version": "1.0"})
    hooks_list = data.get("hooks", [])
    changed = False

    for h in hooks_list:
        name = h.get("name", "")
        should_be_managed = name in settings_hooks
        if h.get("managed") != should_be_managed:
            h["managed"] = should_be_managed
            changed = True

    if changed:
        data["hooks"] = hooks_list
        write_json(HOOK_REGISTRY, data)


# ---------------------------------------------------------------------------
# Output and main run function
# ---------------------------------------------------------------------------

def _print_header():
    """Print the discovery banner."""
    print()
    print("=" * 52)
    print("  Super-Manager Discovery")
    print("=" * 52)
    print()


def _status_label(status):
    """Return fixed-width formatted status label for display."""
    labels = {
        "managed":        "[MANAGED]       ",
        "registered":     "[REGISTERED]    ",
        "orphaned":       "[ORPHANED]      ",
        "new":            "[REGISTERED]    ",
        "no_frontmatter": "[NO FRONTMATTER]",
    }
    return labels.get(status, "[{}]".format(status.upper()))


def run(report_only=False):
    """
    Main discovery function.

    report_only=False: discover and auto-register everything found
    report_only=True:  scan only, print report, make no changes
    """
    _print_header()

    newly_registered = 0

    # ---- HOOKS ----
    print("HOOKS (scanning {}):".format(HOOKS_DIR))
    settings_hooks = _scan_settings_hooks()
    hooks = discover_hooks()
    if not hooks:
        print("  (none found)")

    managed_h = 0
    registered_h = 0
    orphaned_h = 0

    for h in hooks:
        name = h["name"]
        status = h["status"]
        event = h.get("event", "")
        event_str = " ({})".format(event) if event else ""

        if status == "managed":
            print("  {} {}{}".format(_status_label(status), name, event_str))
            managed_h += 1
            # Auto-register into registry if not already there
            if not report_only and not h.get("in_registry"):
                ok = register_hook(
                    name, event,
                    h.get("command", ""),
                    h.get("matcher", "*"),
                    h.get("async", False),
                )
                if ok:
                    newly_registered += 1
        elif status == "registered":
            print("  {} {}{}".format(_status_label(status), name, event_str))
            registered_h += 1
            # Auto-register into registry if not already there
            if not report_only and not h.get("in_registry"):
                ok = register_hook(name, event, h.get("command", ""), h.get("matcher", "*"))
                if ok:
                    newly_registered += 1
        elif status == "orphaned":
            print("  {} {}{} -- file not on disk".format(_status_label(status), name, event_str))
            orphaned_h += 1

    # Sync managed flags in registry to match settings.json
    if not report_only:
        _sync_hook_managed_flags(settings_hooks)

    print()
    print("  {} managed, {} registered, {} orphaned".format(managed_h, registered_h, orphaned_h))
    print()

    # ---- SKILLS ----
    print("SKILLS (scanning {}):".format(GLOBAL_SKILLS_DIR))
    skills = discover_skills()
    if not skills:
        print("  (none found)")

    managed_s = 0
    registered_s = 0
    orphaned_s = 0

    for s in skills:
        skill_id = s["id"]
        status = s["status"]

        if status == "managed":
            print("  {} {} (enabled)".format(_status_label(status), s.get("name", skill_id)))
            managed_s += 1
        elif status == "registered":
            print("  {} {} (disabled)".format(_status_label(status), s.get("name", skill_id)))
            registered_s += 1
        elif status == "orphaned":
            print("  {} {} -- SKILL.md not on disk".format(_status_label(status), s.get("name", skill_id)))
            orphaned_s += 1
        elif status == "new":
            # Not yet in registry - auto-register with [REGISTERED] label
            print("  {} {}".format(_status_label(status), skill_id))
            registered_s += 1
            if not report_only:
                skill_path = s.get("skill_path", "")
                ok = register_skill(skill_id, skill_path)
                if ok:
                    newly_registered += 1

    print()
    print("  {} managed, {} registered, {} orphaned".format(managed_s, registered_s, orphaned_s))
    print()

    # ---- MCP SERVERS ----
    mcp_results, yaml_path = discover_mcp_servers()
    source_label = yaml_path if yaml_path else "not found"
    print("MCP SERVERS (scanning {}):".format(source_label))
    if not mcp_results:
        if yaml_path is None:
            print("  (servers.yaml not found)")
        else:
            print("  (none found)")

    managed_m = 0
    registered_m = 0

    for m in mcp_results:
        status = m["status"]
        enabled_str = "enabled" if m["enabled"] else "disabled"
        print("  {} {} ({})".format(_status_label(status), m["name"], enabled_str))
        if status == "managed":
            managed_m += 1
        else:
            registered_m += 1

    print()
    print("  {} managed, {} registered".format(managed_m, registered_m))
    print()

    # ---- RULES ----
    print("RULES (scanning {}):".format(RULES_DIR))
    rules = discover_rules()
    if not rules:
        print("  (none found)")

    managed_i = 0
    registered_i = 0
    no_frontmatter_i = 0

    for inst in rules:
        inst_id = inst["id"]
        status = inst["status"]

        if status == "managed":
            print("  {} {} (enabled)".format(_status_label(status), inst_id))
            managed_i += 1
        elif status == "registered":
            enabled_str = "enabled" if inst.get("enabled") else "disabled"
            print("  {} {} ({})".format(_status_label(status), inst_id, enabled_str))
            registered_i += 1
        elif status == "no_frontmatter":
            print("  {} {}".format(_status_label(status), inst.get("file", inst_id)))
            no_frontmatter_i += 1

    print()
    print("  {} managed, {} registered, {} no frontmatter".format(managed_i, registered_i, no_frontmatter_i))
    print()

    # ---- SUMMARY ----
    total_managed = managed_h + managed_s + managed_m + managed_i
    total_registered = registered_h + registered_s + registered_m + registered_i
    total_orphaned = orphaned_h + orphaned_s

    print("-" * 52)
    print("  Total: {} managed, {} registered, {} orphaned".format(
        total_managed, total_registered, total_orphaned
    ))
    if newly_registered > 0:
        print("  Newly registered: {} items".format(newly_registered))
    elif report_only:
        print("  Run without --report to auto-register discovered items.")
    print("-" * 52)
    print()

    log.info("Discovery complete: {} managed, {} registered, {} newly registered".format(
        total_managed, total_registered, newly_registered
    ))

    return {
        "managed": total_managed,
        "registered": total_registered,
        "orphaned": total_orphaned,
        "newly_registered": newly_registered,
        "hooks": hooks,
        "skills": skills,
        "mcp_servers": mcp_results,
        "rules": rules,
    }


if __name__ == "__main__":
    report_mode = "--report" in sys.argv
    run(report_only=report_mode)
