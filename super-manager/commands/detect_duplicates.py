"""
detect_duplicates.py - Find and compare duplicate/overlapping skills and projects.

Scans skill directories for similar names, overlapping keywords, and duplicate functionality.
When duplicates found, provides a detailed comparison to help decide which to keep.

Usage: python -m commands.detect_duplicates [--verbose]
       python -m commands.detect_duplicates --compare <path_a> <path_b>
"""
import sys
import os
import time
import datetime
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.configuration_paths import GLOBAL_SKILLS_DIR
from shared.logger import create_logger

log = create_logger("detect-duplicates")


def _get_file_stats(directory):
    """Get modification time stats for all files in a directory tree."""
    now = time.time()
    one_week = 7 * 86400
    one_month = 30 * 86400
    one_year = 365 * 86400

    stats = {
        "total_files": 0,
        "last_modified": 0,
        "last_modified_file": "",
        "modified_last_week": 0,
        "modified_last_month": 0,
        "modified_last_year": 0,
    }

    if not os.path.isdir(directory):
        return stats

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "node_modules", ".next")]
        for f in files:
            fpath = os.path.join(root, f)
            try:
                mtime = os.path.getmtime(fpath)
            except OSError:
                continue

            stats["total_files"] += 1
            age = now - mtime

            if mtime > stats["last_modified"]:
                stats["last_modified"] = mtime
                stats["last_modified_file"] = os.path.relpath(fpath, directory)

            if age < one_week:
                stats["modified_last_week"] += 1
            if age < one_month:
                stats["modified_last_month"] += 1
            if age < one_year:
                stats["modified_last_year"] += 1

    return stats


def _score_organization(directory):
    """Score a project's folder organization (0-100) with reasons."""
    score = 0
    reasons = []

    if not os.path.isdir(directory):
        return 0, ["Directory does not exist"]

    entries = os.listdir(directory)
    files_at_root = [e for e in entries if os.path.isfile(os.path.join(directory, e))]
    dirs_at_root = [e for e in entries if os.path.isdir(os.path.join(directory, e)) and not e.startswith(".")]

    # Has documentation
    if any(f in entries for f in ("README.md", "SKILL.md", "CLAUDE.md")):
        score += 20
        reasons.append("Has documentation file")
    else:
        reasons.append("Missing documentation (README/SKILL.md)")

    # Has subdirectories (organized into folders)
    if dirs_at_root:
        score += 20
        reasons.append(f"{len(dirs_at_root)} subdirectories")
    else:
        reasons.append("No subdirectories (flat structure)")

    # Root file count
    if len(files_at_root) <= 5:
        score += 20
        reasons.append(f"Clean root ({len(files_at_root)} files)")
    elif len(files_at_root) <= 10:
        score += 10
        reasons.append(f"Moderate root ({len(files_at_root)} files)")
    else:
        reasons.append(f"Cluttered root ({len(files_at_root)} files)")

    # Package structure
    if any(f in entries for f in ("__init__.py", "setup.py", "pyproject.toml", "package.json")):
        score += 20
        reasons.append("Proper package structure")

    # Config files
    if any(f.endswith((".yaml", ".yml", ".json", ".toml", ".cfg")) for f in files_at_root):
        score += 10
        reasons.append("Has config files")

    # Tests
    if "tests" in dirs_at_root or "test" in dirs_at_root:
        score += 10
        reasons.append("Has test directory")

    return min(score, 100), reasons


def compare_projects(path_a, path_b):
    """
    Full comparison of two project directories.
    This is the REUSABLE function for manual duplicate review.
    Call directly: compare_projects('/path/to/proj_a', '/path/to/proj_b')
    """
    name_a = os.path.basename(os.path.normpath(path_a))
    name_b = os.path.basename(os.path.normpath(path_b))

    stats_a = _get_file_stats(path_a)
    stats_b = _get_file_stats(path_b)

    org_a, reasons_a = _score_organization(path_a)
    org_b, reasons_b = _score_organization(path_b)

    fmt_time = lambda t: datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M") if t else "never"
    last_a = fmt_time(stats_a["last_modified"])
    last_b = fmt_time(stats_b["last_modified"])

    col = 35
    print()
    print("=" * 70)
    print(f"  Duplicate Comparison: {name_a} vs {name_b}")
    print("=" * 70)
    print()

    header = f"{'Metric':<25} {name_a:<{col}} {name_b}"
    sep = f"{'-'*25} {'-'*col} {'-'*col}"
    print(header)
    print(sep)
    print(f"{'Total files':<25} {stats_a['total_files']:<{col}} {stats_b['total_files']}")
    print(f"{'Last modified':<25} {last_a:<{col}} {last_b}")

    lmf_a = stats_a["last_modified_file"][:col - 1]
    lmf_b = stats_b["last_modified_file"][:col - 1]
    print(f"{'Last modified file':<25} {lmf_a:<{col}} {lmf_b}")
    print(f"{'Modified last week':<25} {stats_a['modified_last_week']:<{col}} {stats_b['modified_last_week']}")
    print(f"{'Modified last month':<25} {stats_a['modified_last_month']:<{col}} {stats_b['modified_last_month']}")
    print(f"{'Modified last year':<25} {stats_a['modified_last_year']:<{col}} {stats_b['modified_last_year']}")
    print(f"{'Organization score':<25} {org_a:<{col}} {org_b}")
    print()

    print(f"  {name_a} organization:")
    for r in reasons_a:
        print(f"    - {r}")
    print(f"  {name_b} organization:")
    for r in reasons_b:
        print(f"    - {r}")
    print()

    # Build recommendation
    winner = None
    rec_reasons = []

    if stats_a["last_modified"] > stats_b["last_modified"]:
        rec_reasons.append(f"{name_a} was modified more recently")
        winner = name_a
    elif stats_b["last_modified"] > stats_a["last_modified"]:
        rec_reasons.append(f"{name_b} was modified more recently")
        winner = name_b

    if org_a > org_b:
        rec_reasons.append(f"{name_a} has better organization ({org_a} vs {org_b})")
        if not winner:
            winner = name_a
    elif org_b > org_a:
        rec_reasons.append(f"{name_b} has better organization ({org_b} vs {org_a})")
        if not winner:
            winner = name_b

    ma = stats_a["modified_last_month"]
    mb = stats_b["modified_last_month"]
    if ma > mb:
        rec_reasons.append(f"{name_a} more active this month ({ma} vs {mb} files)")
    elif mb > ma:
        rec_reasons.append(f"{name_b} more active this month ({mb} vs {ma} files)")

    if winner:
        print(f"  RECOMMENDATION: Keep {winner}")
        for r in rec_reasons:
            print(f"    - {r}")
    else:
        print("  RECOMMENDATION: Projects are similar - manual review needed")

    print()
    log.info(f"Compared {name_a} vs {name_b}: winner={winner}")
    return {
        "name_a": name_a, "name_b": name_b,
        "stats_a": stats_a, "stats_b": stats_b,
        "org_a": org_a, "org_b": org_b,
        "winner": winner, "reasons": rec_reasons,
    }


def find_skill_duplicates():
    """Scan skill directories for potential duplicates based on name similarity and keyword overlap."""
    from managers.skill_manager import list_all

    result = list_all()
    items = result.get("items", [])

    def normalize(name):
        name = name.lower().replace("-", "").replace("_", "").replace(" ", "")
        for suffix in ("skill", "manager", "lite", "api", "mcp"):
            name = name.replace(suffix, "")
        return name

    # Group by similar normalized names
    name_groups = defaultdict(list)
    for item in items:
        norm = normalize(item.get("name", item.get("id", "")))
        if norm:
            name_groups[norm].append(item)

    duplicates = []

    # Name-based duplicates
    for norm, group in name_groups.items():
        if len(group) > 1:
            names = [g.get("name", g.get("id", "?")) for g in group]
            paths = [g.get("skill_path", "") for g in group]
            duplicates.append({
                "type": "name-similar",
                "items": names,
                "paths": paths,
                "reason": "Similar normalized name",
            })

    # Keyword overlap (3+ shared keywords between any two skills)
    for i, item_a in enumerate(items):
        kw_a = set(k.lower() for k in item_a.get("keywords", []))
        if not kw_a:
            continue
        for item_b in items[i + 1:]:
            kw_b = set(k.lower() for k in item_b.get("keywords", []))
            overlap = kw_a & kw_b
            if len(overlap) >= 3:
                na = item_a.get("name", item_a.get("id", "?"))
                nb = item_b.get("name", item_b.get("id", "?"))
                shared = ", ".join(sorted(overlap)[:5])
                duplicates.append({
                    "type": "keyword-overlap",
                    "items": [na, nb],
                    "reason": f"{len(overlap)} shared keywords: {shared}",
                })

    return duplicates


def run(verbose=False, compare_paths=None):
    """Run duplicate detection. Optionally compare two specific paths."""
    if compare_paths and len(compare_paths) == 2:
        return compare_projects(compare_paths[0], compare_paths[1])

    print()
    print("Super Manager Duplicate Detector")
    print("=" * 60)

    duplicates = find_skill_duplicates()

    if not duplicates:
        print()
        print("  No duplicates or overlapping skills detected.")
        print()
        log.info("Duplicate scan: 0 duplicates found")
        return {"duplicates": []}

    print()
    print(f"  Found {len(duplicates)} potential duplicate(s):")

    for dup in duplicates:
        dtype = dup["type"]
        items = dup["items"]
        reason = dup["reason"]
        print()
        print(f"  [{dtype}] {' <-> '.join(items)}")
        print(f"    Reason: {reason}")

        # If we have paths for both, do full comparison
        if "paths" in dup and len(dup["paths"]) == 2:
            pa = os.path.dirname(dup["paths"][0]) if dup["paths"][0] else ""
            pb = os.path.dirname(dup["paths"][1]) if dup["paths"][1] else ""
            if pa and pb and os.path.isdir(pa) and os.path.isdir(pb):
                compare_projects(pa, pb)
        elif verbose:
            for item_name in items:
                skill_dir = os.path.join(GLOBAL_SKILLS_DIR, item_name)
                if os.path.isdir(skill_dir):
                    stats = _get_file_stats(skill_dir)
                    last = datetime.datetime.fromtimestamp(stats["last_modified"]).strftime("%Y-%m-%d") if stats["last_modified"] else "never"
                    print(f"    {item_name}: {stats['total_files']} files, last modified {last}")

    print()
    log.info(f"Duplicate scan: {len(duplicates)} potential duplicates")
    return {"duplicates": duplicates}


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    compare_paths = None
    if "--compare" in sys.argv:
        idx = sys.argv.index("--compare")
        if idx + 2 < len(sys.argv):
            compare_paths = [sys.argv[idx + 1], sys.argv[idx + 2]]
    run(verbose=verbose, compare_paths=compare_paths)
