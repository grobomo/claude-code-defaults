"""
smoke_skills.py - Verify all skill directories match registry state.

Checks:
  - Each skill directory under ~/.claude/skills/ has a SKILL.md file
  - Each directory skill has a matching entry in skill-registry.json
  - Each registry entry points to a SKILL.md that exists on disk

Returns: {"healthy": [...], "issues": [{item, problem}]}
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.configuration_paths import GLOBAL_SKILLS_DIR, SKILL_REGISTRY


def _load_json(path, default=None):
    """Load a JSON file, returning default on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return default


def run():
    """Verify skill directories and registry entries match."""
    healthy = []
    issues = []

    # Load skill registry
    registry = _load_json(SKILL_REGISTRY)
    if registry is None:
        if not os.path.isfile(SKILL_REGISTRY):
            return {
                "healthy": [],
                "issues": [{"item": "skill-registry.json", "problem": "File not found (system may not be set up yet)"}],
            }
        return {
            "healthy": [],
            "issues": [{"item": "skill-registry.json", "problem": "Invalid JSON"}],
        }

    skills_list = registry.get("skills", [])

    # Build lookup: skill id -> registry entry
    registry_by_id = {}
    for skill in skills_list:
        sid = skill.get("id", "")
        if sid:
            registry_by_id[sid] = skill

    # Check 1: Each registry entry has a valid SKILL.md on disk
    for skill in skills_list:
        sid = skill.get("id", "unknown")
        skill_path = skill.get("skillPath", "")
        enabled = skill.get("enabled", True)

        if not skill_path:
            issues.append({
                "item": sid,
                "problem": "Registry entry has no skillPath",
            })
            continue

        # Normalize path separators
        skill_path_normalized = skill_path.replace("\\", "/")

        if os.path.isfile(skill_path):
            status = "enabled" if enabled else "disabled"
            healthy.append(f"{sid} (registry -> disk OK, {status})")
        else:
            issues.append({
                "item": sid,
                "problem": f"SKILL.md not found at registered path: {skill_path_normalized}",
            })

    # Check 2: Scan global skills directory for unregistered skills
    if os.path.isdir(GLOBAL_SKILLS_DIR):
        skip_dirs = {"archive", "__pycache__", ".git", "node_modules"}
        for entry in sorted(os.listdir(GLOBAL_SKILLS_DIR)):
            if entry in skip_dirs or entry.startswith("."):
                continue
            skill_dir = os.path.join(GLOBAL_SKILLS_DIR, entry)
            if not os.path.isdir(skill_dir):
                continue

            skill_md = os.path.join(skill_dir, "SKILL.md")
            # Also check lowercase
            skill_md_lower = os.path.join(skill_dir, "skill.md")

            has_skill_md = os.path.isfile(skill_md) or os.path.isfile(skill_md_lower)

            if has_skill_md and entry not in registry_by_id:
                issues.append({
                    "item": entry,
                    "problem": f"Skill exists on disk ({skill_dir}) but not in skill-registry.json",
                })
            elif not has_skill_md:
                # Directory exists without SKILL.md -- informational
                issues.append({
                    "item": entry,
                    "problem": f"Skill directory exists but has no SKILL.md: {skill_dir}",
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
