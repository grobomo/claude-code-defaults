"""
show_status.py - Display status dashboard for all 4 managed components.

Calls list_all() on each manager and formats a unified dashboard.
Usage: python -m commands.show_status [--verbose]
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.output_formatter import dashboard, item_list, table
from shared.logger import create_logger

log = create_logger("show-status")


def _load_manager(name, module_path):
    """Safely load a manager module and call list_all()."""
    try:
        mod = __import__(module_path, fromlist=["list_all"])
        result = mod.list_all()
        items = result.get("items", [])
        healthy = sum(1 for i in items if i.get("status") == "healthy" or i.get("enabled", True))
        issues = sum(1 for i in items if "orphan" in str(i.get("status", "")) or "error" in str(i.get("status", "")))
        return {
            "name": name,
            "total": len(items),
            "healthy": healthy,
            "issues": issues,
            "items": items,
            "summary": result.get("summary", ""),
        }
    except Exception as e:
        log.error(f"Failed to load {name}: {e}")
        return {
            "name": name,
            "total": 0,
            "healthy": 0,
            "issues": 1,
            "items": [],
            "summary": f"ERROR: {e}",
        }


def run(verbose=False):
    """Run status check across all 4 managers."""
    managers = [
        ("Hook Manager", "managers.hook_manager"),
        ("Skill Manager", "managers.skill_manager"),
        ("MCP Server Manager", "managers.mcp_server_manager"),
        ("Rule Manager", "managers.rule_manager"),
    ]

    stats = []
    for display_name, module_path in managers:
        stat = _load_manager(display_name, module_path)
        stats.append(stat)

    # Print dashboard
    print(dashboard(stats))

    if verbose:
        for stat in stats:
            if stat["items"]:
                print(f"\n--- {stat['name']} Details ---")
                # Pick columns based on manager type
                if "Hook" in stat["name"]:
                    cols = [("name", "Name"), ("event", "Event"), ("status", "Status")]
                elif "Skill" in stat["name"]:
                    cols = [("name", "Name"), ("enabled", "Enabled"), ("status", "Status")]
                elif "MCP" in stat["name"]:
                    cols = [("name", "Name"), ("enabled", "Enabled"), ("status", "Status")]
                elif "Rule" in stat["name"]:
                    cols = [("id", "ID"), ("enabled", "Enabled"), ("name", "Name")]
                print(item_list(stat["items"], cols))
                print()

    # Summary
    total_items = sum(s["total"] for s in stats)
    total_issues = sum(s["issues"] for s in stats)
    print(f"Total: {total_items} managed items, {total_issues} issues")

    log.info(f"Status check: {total_items} items, {total_issues} issues")
    return stats


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    run(verbose=verbose)
