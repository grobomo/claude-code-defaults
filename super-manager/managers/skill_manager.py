"""
skill_manager.py - Native manager for Claude Code skills.

Reads/writes the skill-registry.json and cross-references with the
~/.claude/skills/ directory on disk to detect orphans, drift, and health issues.

Registry location: ~/.claude/super-manager/registries/skill-registry.json
Skills directory:  ~/.claude/skills/ (each skill is a folder with SKILL.md)
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.configuration_paths import SKILL_REGISTRY, GLOBAL_SKILLS_DIR, REGISTRIES_DIR
from shared.logger import create_logger
from shared.config_file_handler import read_json, write_json

log = create_logger("skill-manager")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_registry():
    """Read skill-registry.json. Returns list of skill dicts."""
    data = read_json(SKILL_REGISTRY, {"skills": []})
    return data.get("skills", [])


def _write_registry(skills_list):
    """Write the registry file atomically."""
    os.makedirs(REGISTRIES_DIR, exist_ok=True)
    data = {
        "skills": [
            {
                "id": s.get("id", s.get("name", "")),
                "name": s.get("name", s.get("id", "")),
                "keywords": s.get("keywords", []),
                "skillPath": s.get("skillPath", ""),
                "enabled": s.get("enabled", True),
            }
            for s in skills_list
        ],
    }
    write_json(SKILL_REGISTRY, data)


def _find_registry_entry(name, skills_list):
    """Find a skill in the registry by name or id."""
    for s in skills_list:
        if s.get("id") == name or s.get("name") == name:
            return s
    return None


def _scan_disk_skills():
    """
    Scan ~/.claude/skills/ for directories containing SKILL.md.
    Returns dict: {skill_dir_name: absolute_path_to_SKILL.md}
    """
    results = {}
    if not os.path.isdir(GLOBAL_SKILLS_DIR):
        return results
    for entry in os.listdir(GLOBAL_SKILLS_DIR):
        skill_dir = os.path.join(GLOBAL_SKILLS_DIR, entry)
        if not os.path.isdir(skill_dir):
            continue
        skill_md = os.path.join(skill_dir, "SKILL.md")
        if os.path.isfile(skill_md):
            results[entry] = skill_md
    return results


def _determine_status(in_registry, on_disk, enabled):
    """Determine the health status of a skill."""
    if in_registry and on_disk and enabled:
        return "healthy"
    if in_registry and on_disk and not enabled:
        return "disabled"
    if in_registry and not on_disk:
        return "orphaned-registry"
    if not in_registry and on_disk:
        return "orphaned-disk"
    return "unknown"


# ---------------------------------------------------------------------------
# Public API - Standard manager interface
# ---------------------------------------------------------------------------

def list_all():
    """
    Read skills from BOTH registry and disk. Cross-reference them.
    Returns {"items": [...], "summary": "25 skills (20 healthy, ...)"}
    Each item: {name, id, enabled, keywords, skill_path, in_registry, on_disk, status}
    """
    log.debug("list_all: reading skill-registry.json and scanning disk")
    registry_skills = _read_registry()
    disk_skills = _scan_disk_skills()
    seen_names = set()
    items = []

    # Registry skills first (they carry metadata)
    for rs in registry_skills:
        skill_id = rs.get("id", rs.get("name", ""))
        skill_name = rs.get("name", skill_id)
        seen_names.add(skill_id)
        if skill_name != skill_id:
            seen_names.add(skill_name)

        skill_path = rs.get("skillPath", "")
        enabled = rs.get("enabled", True)
        keywords = rs.get("keywords", [])

        # Check if on disk: match by id against disk directory names,
        # or by checking if the skillPath file actually exists
        on_disk = False
        if skill_id in disk_skills:
            on_disk = True
            if not skill_path:
                skill_path = disk_skills[skill_id]
        elif skill_path and os.path.isfile(skill_path):
            on_disk = True

        status = _determine_status(True, on_disk, enabled)

        items.append({
            "name": skill_name,
            "id": skill_id,
            "enabled": enabled,
            "keywords": keywords,
            "skill_path": skill_path,
            "in_registry": True,
            "on_disk": on_disk,
            "status": status,
        })

    # Disk skills not in registry (orphaned-disk)
    for dir_name, skill_md_path in disk_skills.items():
        if dir_name in seen_names:
            continue
        seen_names.add(dir_name)
        items.append({
            "name": dir_name,
            "id": dir_name,
            "enabled": False,
            "keywords": [],
            "skill_path": skill_md_path,
            "in_registry": False,
            "on_disk": True,
            "status": "orphaned-disk",
        })

    total = len(items)
    healthy = sum(1 for i in items if i["status"] == "healthy")
    disabled = sum(1 for i in items if i["status"] == "disabled")
    orphaned_reg = sum(1 for i in items if i["status"] == "orphaned-registry")
    orphaned_disk = sum(1 for i in items if i["status"] == "orphaned-disk")

    parts = ["{} skills".format(total)]
    if healthy:
        parts.append("{} healthy".format(healthy))
    if disabled:
        parts.append("{} disabled".format(disabled))
    if orphaned_reg:
        parts.append("{} orphaned-registry".format(orphaned_reg))
    if orphaned_disk:
        parts.append("{} orphaned-disk".format(orphaned_disk))

    summary = ", ".join(parts)
    log.info("list_all: {}".format(summary))
    return {"items": items, "summary": summary}


def add_item(name, skill_path, description="", keywords=None):
    """
    Register a skill in skill-registry.json.
    Returns {"success": bool, "message": str}
    """
    if not name or not name.strip():
        msg = "Skill name cannot be empty"
        log.error("add_item: {}".format(msg))
        return {"success": False, "message": msg}

    if keywords is None:
        keywords = [name]

    registry_skills = _read_registry()
    existing = _find_registry_entry(name, registry_skills)
    if existing:
        msg = "Skill {} already exists in registry".format(repr(name))
        log.warn("add_item: {}".format(msg))
        return {"success": False, "message": msg}

    skill_path = os.path.normpath(skill_path) if skill_path else ""

    file_warning = ""
    if skill_path and not os.path.isfile(skill_path):
        file_warning = " [WARNING: SKILL.md not found at {}]".format(skill_path)
        log.warn("add_item: SKILL.md not found for {}: {}".format(repr(name), skill_path))

    registry_skills.append({
        "id": name,
        "name": name,
        "keywords": keywords,
        "skillPath": skill_path,
        "enabled": True,
    })
    _write_registry(registry_skills)
    log.info("add_item: registered skill {} (path={})".format(repr(name), skill_path))

    msg = "Added skill {}{}".format(repr(name), file_warning)
    return {"success": True, "message": msg}


def remove_item(name):
    """
    Remove skill from registry (does NOT delete files on disk).
    Returns {"success": bool, "message": str}
    """
    log.info("remove_item: removing {}".format(repr(name)))
    registry_skills = _read_registry()
    entry = _find_registry_entry(name, registry_skills)

    if not entry:
        msg = "Skill {} not found in registry".format(repr(name))
        log.error("remove_item: {}".format(msg))
        return {"success": False, "message": msg}

    registry_skills = [
        s for s in registry_skills
        if s.get("id") != name and s.get("name") != name
    ]
    _write_registry(registry_skills)
    log.info("remove_item: removed {} from skill-registry.json".format(repr(name)))

    msg = "Removed skill {} from registry (files on disk untouched)".format(repr(name))
    return {"success": True, "message": msg}


def enable_item(name):
    """
    Set enabled=True for a skill in the registry.
    Returns {"success": bool, "message": str}
    """
    registry_skills = _read_registry()
    entry = _find_registry_entry(name, registry_skills)

    if not entry:
        msg = "Skill {} not found in registry".format(repr(name))
        log.error("enable_item: {}".format(msg))
        return {"success": False, "message": msg}

    if entry.get("enabled", True):
        msg = "Skill {} is already enabled".format(repr(name))
        log.info("enable_item: {}".format(msg))
        return {"success": True, "message": msg}

    entry["enabled"] = True
    _write_registry(registry_skills)
    log.info("enable_item: enabled skill {}".format(repr(name)))
    return {"success": True, "message": "Enabled skill {}".format(repr(name))}


def disable_item(name):
    """
    Set enabled=False for a skill in the registry.
    Returns {"success": bool, "message": str}
    """
    registry_skills = _read_registry()
    entry = _find_registry_entry(name, registry_skills)

    if not entry:
        msg = "Skill {} not found in registry".format(repr(name))
        log.error("disable_item: {}".format(msg))
        return {"success": False, "message": msg}

    if not entry.get("enabled", True):
        msg = "Skill {} is already disabled".format(repr(name))
        log.info("disable_item: {}".format(msg))
        return {"success": True, "message": msg}

    entry["enabled"] = False
    _write_registry(registry_skills)
    log.info("disable_item: disabled skill {}".format(repr(name)))
    return {"success": True, "message": "Disabled skill {}".format(repr(name))}


def verify_all():
    """
    Health check: cross-reference registry with disk.
    Returns {"healthy": [...], "issues": [...]}
    Each issue: {"item": str, "problem": str, "fix": str}
    """
    log.debug("verify_all: running health check")
    registry_skills = _read_registry()
    disk_skills = _scan_disk_skills()
    healthy = []
    issues = []
    seen_on_disk = set()

    for rs in registry_skills:
        skill_id = rs.get("id", rs.get("name", ""))
        skill_name = rs.get("name", skill_id)
        skill_path = rs.get("skillPath", "")
        enabled = rs.get("enabled", True)

        on_disk = False
        if skill_id in disk_skills:
            on_disk = True
            seen_on_disk.add(skill_id)
        elif skill_path and os.path.isfile(skill_path):
            on_disk = True
            for dk in disk_skills:
                if disk_skills[dk] == os.path.normpath(skill_path):
                    seen_on_disk.add(dk)
                    break

        if on_disk and enabled:
            healthy.append(skill_name)
        elif on_disk and not enabled:
            issues.append({
                "item": skill_name,
                "problem": "Skill is disabled in registry but exists on disk",
                "fix": "Run enable_item({}) to re-enable".format(repr(skill_id)),
            })
        elif not on_disk and enabled:
            issues.append({
                "item": skill_name,
                "problem": "Registered and enabled but SKILL.md not found on disk",
                "fix": "Check skill_path or run remove_item({}) to clean up".format(
                    repr(skill_id)
                ),
            })
        elif not on_disk and not enabled:
            issues.append({
                "item": skill_name,
                "problem": "Registered but disabled and SKILL.md not found on disk",
                "fix": "Run remove_item({}) to clean up stale entry".format(
                    repr(skill_id)
                ),
            })

    # Disk skills not in registry
    for dir_name, skill_md_path in disk_skills.items():
        if dir_name in seen_on_disk:
            continue
        issues.append({
            "item": dir_name,
            "problem": "Skill directory exists on disk but not registered",
            "fix": "Run add_item({}, {}) to register".format(
                repr(dir_name), repr(skill_md_path)
            ),
        })

    log.info("verify_all: {} healthy, {} issues".format(len(healthy), len(issues)))
    return {"healthy": healthy, "issues": issues}
