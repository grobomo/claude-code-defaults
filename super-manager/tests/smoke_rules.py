"""
smoke_rules.py - Verify all rule files have valid structure.

Checks:
  - Scans ~/.claude/rules/UserPromptSubmit/*.md and Stop/*.md
  - Each file has valid YAML frontmatter (id, name, keywords, enabled)
  - Keywords list is non-empty
  - No duplicate IDs across files

Returns: {"healthy": [...], "issues": [{item, problem}]}
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.configuration_paths import RULES_DIR

# Subdirectories to scan for rule files
RULE_SUBDIRS = ["UserPromptSubmit", "Stop"]

# Required frontmatter fields (all rules need id + enabled)
# UserPromptSubmit rules use "keywords", Stop rules use "pattern"
REQUIRED_FIELDS_COMMON = ["id", "enabled"]
# At least one of these trigger fields must be present
TRIGGER_FIELDS = ["keywords", "pattern"]


def _parse_frontmatter(file_path):
    """
    Parse YAML frontmatter from a markdown file.
    Returns (dict, error_string). Dict is None on parse failure.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (IOError, UnicodeDecodeError) as e:
        return None, f"Cannot read file: {e}"

    if not content.strip():
        return None, "File is empty"

    # Check for frontmatter delimiters (--- at start)
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None, "No YAML frontmatter found (missing --- delimiters)"

    frontmatter_text = match.group(1)

    # Simple YAML parser for flat key-value pairs (no external deps)
    result = {}
    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Handle key: value pairs
        colon_idx = line.find(":")
        if colon_idx == -1:
            continue

        key = line[:colon_idx].strip()
        value = line[colon_idx + 1:].strip()

        # Handle YAML list syntax: [item1, item2, item3]
        if value.startswith("[") and value.endswith("]"):
            items = value[1:-1].split(",")
            result[key] = [item.strip().strip('"').strip("'") for item in items if item.strip()]
        # Handle boolean
        elif value.lower() in ("true", "false"):
            result[key] = value.lower() == "true"
        # Handle number
        elif value.isdigit():
            result[key] = int(value)
        else:
            result[key] = value.strip('"').strip("'")

    return result, None


def run():
    """Verify all rule files have valid YAML frontmatter."""
    healthy = []
    issues = []
    seen_ids = {}

    if not os.path.isdir(RULES_DIR):
        return {
            "healthy": [],
            "issues": [{"item": "rules/", "problem": "Rules directory not found (system may not be set up yet)"}],
        }

    for subdir in RULE_SUBDIRS:
        subdir_path = os.path.join(RULES_DIR, subdir)
        if not os.path.isdir(subdir_path):
            # Not an error -- subdir may not exist yet
            healthy.append(f"{subdir}/ (directory not created yet, skipped)")
            continue

        for filename in sorted(os.listdir(subdir_path)):
            if not filename.endswith(".md"):
                continue
            if filename.startswith("."):
                continue

            file_path = os.path.join(subdir_path, filename)
            display_name = f"{subdir}/{filename}"

            if not os.path.isfile(file_path):
                continue

            # Parse frontmatter
            fm, error = _parse_frontmatter(file_path)
            if error:
                issues.append({"item": display_name, "problem": error})
                continue

            # Check required common fields
            missing = [f for f in REQUIRED_FIELDS_COMMON if f not in fm]
            if missing:
                issues.append({
                    "item": display_name,
                    "problem": f"Missing required frontmatter fields: {', '.join(missing)}",
                })
                continue

            # Check that at least one trigger field is present (keywords or pattern)
            has_trigger = any(f in fm for f in TRIGGER_FIELDS)
            if not has_trigger:
                issues.append({
                    "item": display_name,
                    "problem": f"Missing trigger field: needs one of {', '.join(TRIGGER_FIELDS)}",
                })
                continue

            # Validate keywords if present (must be non-empty list)
            trigger_desc = ""
            if "keywords" in fm:
                keywords = fm["keywords"]
                if not isinstance(keywords, list):
                    issues.append({
                        "item": display_name,
                        "problem": f"Keywords should be a list, got: {type(keywords).__name__}",
                    })
                    continue
                if len(keywords) == 0:
                    issues.append({
                        "item": display_name,
                        "problem": "Keywords list is empty",
                    })
                    continue
                trigger_desc = f"{len(keywords)} keywords"

            # Validate pattern if present (must be non-empty string)
            if "pattern" in fm:
                pattern = fm["pattern"]
                if not isinstance(pattern, str) or not pattern.strip():
                    issues.append({
                        "item": display_name,
                        "problem": "Pattern field is empty or not a string",
                    })
                    continue
                trigger_desc = f"pattern ({len(pattern)} chars)"

            # Check for duplicate IDs
            file_id = fm.get("id", "")
            if file_id in seen_ids:
                issues.append({
                    "item": display_name,
                    "problem": f"Duplicate id '{file_id}' (also in {seen_ids[file_id]})",
                })
                continue
            seen_ids[file_id] = display_name

            # All checks passed
            enabled = fm.get("enabled", True)
            status = "enabled" if enabled else "disabled"
            healthy.append(f"{display_name} (id={file_id}, {trigger_desc}, {status})")

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
