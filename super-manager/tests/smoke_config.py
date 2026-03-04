"""
smoke_config.py - Verify config sync state (repos, installed state, cached clones).

Checks:
  - installed.json is valid JSON (if exists)
  - repos.json is valid JSON (if exists)
  - Each registered repo has a cached clone directory
  - Each installed repo's version and categories are present

Returns: {"healthy": [...], "issues": [{item, problem}]}
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.configuration_paths import (
    CONFIG_DIR,
    CONFIG_INSTALLED_JSON,
    CONFIG_REPOS_DIR,
    CONFIG_REPOS_JSON,
)


def _load_json(path, default=None):
    """Load a JSON file, returning default on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return default


def _repo_slug(owner_repo):
    """Convert 'owner/repo' to 'owner--repo' for filesystem use."""
    return owner_repo.replace("/", "--")


def run():
    """Verify config sync state files and cached repo clones."""
    healthy = []
    issues = []

    # If config dir doesn't exist at all, system hasn't been set up
    if not os.path.isdir(CONFIG_DIR):
        return {
            "healthy": ["config/ directory not created yet (no config sync set up)"],
            "issues": [],
        }

    # Check 1: installed.json
    if os.path.isfile(CONFIG_INSTALLED_JSON):
        installed = _load_json(CONFIG_INSTALLED_JSON)
        if installed is not None:
            repo_count = len(installed)
            total_items = 0
            for slug, state in installed.items():
                for cat_items in state.get("categories", {}).values():
                    total_items += len(cat_items)
            healthy.append(f"installed.json valid ({repo_count} repos, {total_items} items)")
        else:
            issues.append({
                "item": "installed.json",
                "problem": "File exists but is not valid JSON",
            })
    else:
        # Not an error -- just no imports done yet
        healthy.append("installed.json not present (no config imports done yet)")

    # Check 2: repos.json
    repos = []
    if os.path.isfile(CONFIG_REPOS_JSON):
        repos_data = _load_json(CONFIG_REPOS_JSON)
        if repos_data is not None:
            if isinstance(repos_data, list):
                repos = repos_data
                healthy.append(f"repos.json valid ({len(repos)} repos registered)")
            else:
                issues.append({
                    "item": "repos.json",
                    "problem": f"repos.json should be a list, got {type(repos_data).__name__}",
                })
        else:
            issues.append({
                "item": "repos.json",
                "problem": "File exists but is not valid JSON",
            })
    else:
        healthy.append("repos.json not present (no config repos registered yet)")

    # Check 3: Each registered repo has a cached clone
    for repo_entry in repos:
        owner_repo = repo_entry.get("owner_repo", "")
        if not owner_repo:
            issues.append({
                "item": "repos.json entry",
                "problem": "Repo entry missing 'owner_repo' field",
            })
            continue

        slug = _repo_slug(owner_repo)
        clone_dir = os.path.join(CONFIG_REPOS_DIR, slug)

        if os.path.isdir(clone_dir):
            # Check if it's a valid git clone
            git_dir = os.path.join(clone_dir, ".git")
            if os.path.isdir(git_dir) or os.path.isfile(git_dir):
                healthy.append(f"repo clone: {owner_repo} (cached at {slug}/)")
            else:
                issues.append({
                    "item": owner_repo,
                    "problem": f"Clone directory exists but is not a git repo: {clone_dir}",
                })
        else:
            issues.append({
                "item": owner_repo,
                "problem": f"Registered repo has no cached clone at {clone_dir}",
            })

    # Check 4: Each installed repo's state has required fields
    installed = _load_json(CONFIG_INSTALLED_JSON, {})
    if isinstance(installed, dict):
        for slug, state in installed.items():
            if not isinstance(state, dict):
                issues.append({
                    "item": slug,
                    "problem": "Installed state is not a dict",
                })
                continue

            owner_repo = state.get("owner_repo", slug)
            version = state.get("version")
            installed_at = state.get("installed_at")
            categories = state.get("categories", {})

            if not version:
                issues.append({
                    "item": owner_repo,
                    "problem": "Installed state missing 'version' field",
                })
            if not installed_at:
                issues.append({
                    "item": owner_repo,
                    "problem": "Installed state missing 'installed_at' timestamp",
                })
            if not categories:
                issues.append({
                    "item": owner_repo,
                    "problem": "Installed state has no categories (empty install?)",
                })
            else:
                healthy.append(f"installed: {owner_repo} v{version} ({len(categories)} categories)")

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
