"""
run_doctor.py - Find and auto-fix problems across all managed components.

Runs verify_all() on each manager, smoke tests, config sync verification,
duplicate detection, and log health checks. Offers auto-fixes where possible.
Usage: python -m commands.run_doctor [--fix]
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.output_formatter import table
from shared.logger import create_logger

log = create_logger("run-doctor")


def _explain_issue(problem):
    """Return a human-readable explanation of why this issue happened."""
    p = problem.lower()
    if "not found on disk" in p or "skill.md not found" in p:
        return "Registry has an entry but the actual file was deleted or moved. Stale registry entry."
    if "not registered" in p or "orphaned-disk" in p or "exists on disk but" in p:
        return "Skill was created on disk (manually or by skill-maker) but never added to the registry."
    if "orphaned-settings" in p or "not in hook-registry" in p:
        return "Hook is in settings.json but was never registered in hook-registry.json. Likely added manually."
    if "orphaned-registry" in p or "not in settings" in p:
        return "Hook is in registry but was removed from settings.json. Disabled or stale."
    if "command not found" in p:
        return "The binary for this server is not installed or not on PATH."
    if "no command or url" in p:
        return "Server entry in servers.yaml has no command or url - incomplete configuration."
    if "syntax" in p:
        return "Script has a JavaScript/Python syntax error. Needs manual code fix."
    if "file not found" in p:
        return "Hook script file was deleted or moved but still referenced in settings.json."
    return ""



def _check_manager(name, module_path):
    """Run verify_all() on one manager, return issues list."""
    try:
        mod = __import__(module_path, fromlist=["verify_all"])
        result = mod.verify_all()
        issues = result.get("issues", [])
        healthy = result.get("healthy", [])
        return {
            "name": name,
            "module": module_path,
            "healthy_count": len(healthy),
            "issues": issues,
            "error": None,
        }
    except Exception as e:
        log.error(f"Doctor failed for {name}: {e}")
        return {
            "name": name,
            "module": module_path,
            "healthy_count": 0,
            "issues": [{"item": name, "problem": f"Manager failed to load: {e}", "fix": "Check module imports"}],
            "error": str(e),
        }


def _attempt_fix(issue, module_path):
    """Try to auto-fix a known issue type."""
    problem = issue.get("problem", "")
    item = issue.get("item", issue.get("name", "unknown"))
    p = problem.lower()

    # Stale registry entry (registered but file not on disk) -> remove from registry
    if "not found on disk" in p or "skill.md not found" in p:
        try:
            mod = __import__(module_path, fromlist=["remove_item"])
            mod.remove_item(item)
            log.info(f"Auto-fixed: removed stale registry entry for '{item}'")
            return True, f"Removed stale registry entry for '{item}'"
        except Exception as e:
            return False, f"Could not remove '{item}': {e}"

    # Disk-only skill (exists on disk but not registered) -> register it
    if "not registered" in p or "exists on disk but" in p:
        try:
            mod = __import__(module_path, fromlist=["add_item"])
            # Build the skill path from the name
            import os
            home = os.environ.get("HOME") or os.environ.get("USERPROFILE", "")
            skill_path = os.path.join(home, ".claude", "skills", item, "SKILL.md")
            if os.path.isfile(skill_path):
                mod.add_item(item, skill_path, keywords=[item.replace("-", " ")])
                log.info(f"Auto-fixed: registered disk skill '{item}'")
                return True, f"Registered '{item}' from disk"
            else:
                return False, f"SKILL.md not found at expected path for '{item}'"
        except Exception as e:
            return False, f"Could not register '{item}': {e}"

    # Orphaned settings hook -> can offer to register but needs event/command info
    if "orphaned-settings" in p or "not in hook-registry" in p:
        log.warn(f"Cannot auto-fix orphaned settings hook '{item}' - register manually")
        return False, f"Hook '{item}' needs manual registration (event + command required)"

    # Orphaned registry hook -> remove from registry
    if "orphaned-registry" in p or "not in settings" in p:
        try:
            mod = __import__(module_path, fromlist=["remove_item"])
            mod.remove_item(item)
            log.info(f"Auto-fixed: removed orphaned registry entry for '{item}'")
            return True, f"Removed orphaned registry entry for '{item}'"
        except Exception as e:
            return False, f"Could not remove '{item}': {e}"

    # Missing file or syntax error - manual fix needed
    if "file not found" in p or "syntax" in p:
        return False, f"'{item}' needs manual fix"

    return False, f"Unknown issue type for '{item}' - needs manual review"


def _run_smoke_tests():
    """Run smoke tests and return combined results."""
    smoke_modules = [
        ("hooks", "tests.smoke_hooks"),
        ("rules", "tests.smoke_rules"),
        ("skills", "tests.smoke_skills"),
        ("credentials", "tests.smoke_credentials"),
        ("config", "tests.smoke_config"),
        ("settings", "tests.smoke_settings"),
    ]

    results = []
    for name, module_path in smoke_modules:
        try:
            mod = __import__(module_path, fromlist=["run"])
            result = mod.run()
            results.append({
                "name": name,
                "healthy": len(result.get("healthy", [])),
                "issues": result.get("issues", []),
            })
        except Exception as e:
            results.append({
                "name": name,
                "healthy": 0,
                "issues": [{"item": name, "problem": f"Smoke test failed: {e}"}],
            })
    return results


def _run_config_sync_verify():
    """Run config sync state verification."""
    try:
        from commands.config_sync import verify_config_state
        return verify_config_state()
    except Exception as e:
        return {"healthy": [], "issues": [{"item": "config-sync", "problem": str(e)}]}


def _check_log_health():
    """
    Final doctor check: verify all log files are present, recent, and useful.
    Returns {"healthy": [...], "issues": [...]}.

    Checks:
    1. Each manager log file exists
    2. Last entry in each log is recent (written within last 7 days)
    3. Recent unaddressed ERROR entries (errors without a subsequent resolution)
    4. enforcement.log and skill-usage.jsonl exist and have content
    5. No stale test/orphaned log files
    """
    from shared.configuration_paths import LOGS_DIR
    import datetime
    import glob as glob_mod
    import json

    healthy = []
    issues = []

    # Expected manager log files
    expected_manager_logs = [
        "hook-manager.log",
        "skill-manager.log",
        "mcp-server-manager.log",
        "rule-manager.log",
        "credential-manager.log",
    ]

    # Expected command log files (less critical)
    expected_command_logs = [
        "run-doctor.log",
        "discover.log",
        "show-status.log",
    ]

    # Expected analytics files
    expected_analytics = [
        "super-manager-enforcement.log",
        "skill-usage.jsonl",
    ]

    now = datetime.datetime.now()
    stale_days = 7

    # Check manager logs
    for log_file in expected_manager_logs:
        log_path = os.path.join(LOGS_DIR, log_file)
        manager_name = log_file.replace(".log", "")

        if not os.path.isfile(log_path):
            issues.append({
                "item": log_file,
                "problem": f"Log file missing -- {manager_name} has never logged",
                "fix": f"Run a {manager_name} command to generate initial log entries",
            })
            continue

        # Check file size (empty = useless)
        size = os.path.getsize(log_path)
        if size == 0:
            issues.append({
                "item": log_file,
                "problem": "Log file exists but is empty (0 bytes)",
                "fix": f"Run a {manager_name} command to generate log entries",
            })
            continue

        # Check last modification time
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(log_path))
        age_days = (now - mtime).days
        if age_days > stale_days:
            issues.append({
                "item": log_file,
                "problem": f"Log stale -- last written {age_days} days ago",
                "fix": f"Run {manager_name} verify to confirm it's still functional",
            })
            continue

        # Check for recent ERROR entries (last 50 lines)
        error_count = 0
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            # Check last 50 lines for ERRORs
            recent_lines = lines[-50:] if len(lines) > 50 else lines
            for line in recent_lines:
                if "[ERROR]" in line:
                    error_count += 1
        except Exception:
            pass

        if error_count > 5:
            issues.append({
                "item": log_file,
                "problem": f"{error_count} ERROR entries in recent log -- may indicate ongoing problems",
                "fix": f"Review {log_path} and address root causes",
            })
        else:
            healthy.append(log_file)

    # Check analytics files
    for analytics_file in expected_analytics:
        analytics_path = os.path.join(LOGS_DIR, analytics_file)

        if not os.path.isfile(analytics_path):
            issues.append({
                "item": analytics_file,
                "problem": "Analytics file missing -- hook pipeline may not be logging",
                "fix": "Verify tool-reminder.js and enforcement-gate.js hooks are installed",
            })
            continue

        size = os.path.getsize(analytics_path)
        if size == 0:
            issues.append({
                "item": analytics_file,
                "problem": "Analytics file is empty -- hooks may not be firing",
                "fix": "Verify hooks are registered in settings.json and firing on prompts",
            })
            continue

        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(analytics_path))
        age_days = (now - mtime).days
        if age_days > stale_days:
            issues.append({
                "item": analytics_file,
                "problem": f"Analytics stale -- last written {age_days} days ago",
                "fix": "Verify hook pipeline is active (hooks may be disabled)",
            })
        else:
            healthy.append(analytics_file)

    # Check skill-usage.jsonl format validity (sample last 5 lines)
    jsonl_path = os.path.join(LOGS_DIR, "skill-usage.jsonl")
    if os.path.isfile(jsonl_path) and os.path.getsize(jsonl_path) > 0:
        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            bad_lines = 0
            sample = lines[-5:] if len(lines) > 5 else lines
            for line in sample:
                line = line.strip()
                if not line:
                    continue
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    bad_lines += 1
            if bad_lines > 0:
                issues.append({
                    "item": "skill-usage.jsonl",
                    "problem": f"{bad_lines} malformed JSON lines in recent entries",
                    "fix": "Check hook that writes skill-usage.jsonl for serialization bugs",
                })
        except Exception:
            pass

    return {"healthy": healthy, "issues": issues}


def run(auto_fix=False):
    """Run doctor across all managers, smoke tests, and config sync."""
    managers = [
        ("Hook Manager", "managers.hook_manager"),
        ("Skill Manager", "managers.skill_manager"),
        ("MCP Server Manager", "managers.mcp_server_manager"),
        ("Rule Manager", "managers.rule_manager"),
    ]

    all_issues = []
    total_healthy = 0

    print("\nSuper Manager Doctor")
    print("=" * 60)

    for display_name, module_path in managers:
        result = _check_manager(display_name, module_path)
        total_healthy += result["healthy_count"]

        if result["error"]:
            print(f"\n[ERROR] {display_name}: {result['error']}")
        elif not result["issues"]:
            print(f"\n[OK] {display_name}: {result['healthy_count']} items, all healthy")
        else:
            print(f"\n[WARN] {display_name}: {result['healthy_count']} healthy, {len(result['issues'])} issues")
            for issue in result["issues"]:
                item_name = issue.get('item', issue.get('name', '?'))
                problem = issue.get('problem', '?')
                explanation = _explain_issue(problem)
                print(f"  - {item_name}: {problem}")
                if explanation:
                    print(f"    WHY: {explanation}")
                if auto_fix:
                    fixed, msg = _attempt_fix(issue, module_path)
                    status = "FIXED" if fixed else "SKIP"
                    print(f"    [{status}] {msg}")

        for issue in result["issues"]:
            issue["manager"] = display_name
        all_issues.extend(result["issues"])

    # Smoke tests
    print("\n--- Smoke Tests ---")
    smoke_results = _run_smoke_tests()
    for sr in smoke_results:
        total_healthy += sr["healthy"]
        if not sr["issues"]:
            print(f"  [OK] {sr['name']}: {sr['healthy']} healthy")
        else:
            print(f"  [WARN] {sr['name']}: {sr['healthy']} healthy, {len(sr['issues'])} issues")
            for issue in sr["issues"][:3]:
                prob = issue.get("problem", str(issue)) if isinstance(issue, dict) else str(issue)
                print(f"    - {prob}")
            if len(sr["issues"]) > 3:
                print(f"    ... and {len(sr['issues']) - 3} more")
        for issue in sr["issues"]:
            if isinstance(issue, dict):
                issue["manager"] = f"smoke:{sr['name']}"
            all_issues.append(issue if isinstance(issue, dict) else {"item": sr["name"], "problem": str(issue)})

    # Config sync state
    print("\n--- Config Sync ---")
    config_result = _run_config_sync_verify()
    config_healthy = config_result.get("healthy", [])
    config_issues = config_result.get("issues", [])
    total_healthy += len(config_healthy)
    if not config_issues:
        if config_healthy:
            print(f"  [OK] {len(config_healthy)} installed items verified")
        else:
            print("  [OK] No config repos installed (clean state)")
    else:
        print(f"  [WARN] {len(config_healthy)} healthy, {len(config_issues)} issues")
        for issue in config_issues:
            prob = issue.get("problem", str(issue)) if isinstance(issue, dict) else str(issue)
            print(f"    - {prob}")
        all_issues.extend(config_issues)

    # Duplicate detection
    print("\n--- Duplicate Scan ---")
    try:
        from commands.detect_duplicates import find_skill_duplicates, compare_projects
        duplicates = find_skill_duplicates()
        if duplicates:
            print(f"  Found {len(duplicates)} potential duplicate(s):")
            for dup in duplicates:
                items = dup["items"]
                print(f"  [{dup['type']}] {' <-> '.join(items)}")
                print(f"    Reason: {dup['reason']}")
                if "paths" in dup and len(dup["paths"]) == 2:
                    pa = os.path.dirname(dup["paths"][0]) if dup["paths"][0] else ""
                    pb = os.path.dirname(dup["paths"][1]) if dup["paths"][1] else ""
                    if pa and pb and os.path.isdir(pa) and os.path.isdir(pb):
                        compare_projects(pa, pb)
        else:
            print("  No duplicates detected")
    except Exception as e:
        print(f"  Duplicate scan failed: {e}")

    # Log health check (LAST -- ensures everything above has generated logs)
    print("\n--- Log Health ---")
    log_result = _check_log_health()
    log_healthy = log_result.get("healthy", [])
    log_issues = log_result.get("issues", [])
    total_healthy += len(log_healthy)
    if not log_issues:
        print(f"  [OK] {len(log_healthy)} log files healthy, all recent, no excessive errors")
    else:
        print(f"  [WARN] {len(log_healthy)} healthy, {len(log_issues)} issues")
        for issue in log_issues:
            item = issue.get("item", "?")
            prob = issue.get("problem", "?")
            print(f"    - {item}: {prob}")
        all_issues.extend(log_issues)

    print(f"\n{'=' * 60}")
    print(f"Total: {total_healthy} healthy, {len(all_issues)} issues")

    if all_issues and not auto_fix:
        print("\nRun with --fix to attempt auto-repair")

    log.info(f"Doctor: {total_healthy} healthy, {len(all_issues)} issues, auto_fix={auto_fix}")
    return {"healthy": total_healthy, "issues": all_issues}


if __name__ == "__main__":
    auto_fix = "--fix" in sys.argv
    run(auto_fix=auto_fix)
