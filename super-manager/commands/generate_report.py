"""
generate_report.py - Generate a markdown config report for all 4 components.

Writes to ~/.claude/super-manager/reports/config-report.md
This replaces the old config-awareness.js report at ~/.claude/config-report.md
Usage: python -m commands.generate_report
"""
import sys
import os
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.configuration_paths import CONFIG_REPORT, REPORTS_DIR
from shared.file_operations import atomic_write, ensure_directory
from shared.logger import create_logger

log = create_logger("generate-report")


def _load_items(module_path):
    """Load items from a manager module."""
    try:
        mod = __import__(module_path, fromlist=["list_all"])
        result = mod.list_all()
        return result.get("items", []), result.get("summary", "")
    except Exception as e:
        return [], f"ERROR: {e}"


def run():
    """Generate the full markdown report."""
    ensure_directory(REPORTS_DIR)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = []
    lines.append("# Super Manager Configuration Report")
    lines.append(f"\nGenerated: {now}")
    lines.append("")

    managers = [
        ("Hooks", "managers.hook_manager", [
            ("Name", "name"), ("Event", "event"), ("Status", "status"),
        ]),
        ("Skills", "managers.skill_manager", [
            ("Name", "name"), ("Enabled", "enabled"), ("Status", "status"),
        ]),
        ("MCP Servers", "managers.mcp_server_manager", [
            ("Name", "name"), ("Enabled", "enabled"), ("Status", "status"),
        ]),
        ("Rules", "managers.rule_manager", [
            ("ID", "id"), ("Enabled", "enabled"), ("Name", "name"),
        ]),
    ]

    summary_parts = []

    for section_name, module_path, columns in managers:
        items, summary = _load_items(module_path)
        summary_parts.append(f"{section_name}: {len(items)}")

        lines.append(f"## {section_name} ({len(items)})")
        lines.append(f"_{summary}_")
        lines.append("")

        if items:
            # Build markdown table
            headers = [col[0] for col in columns]
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join("---" for _ in headers) + " |")
            for item in items:
                cells = []
                for _, key in columns:
                    val = item.get(key, "")
                    if isinstance(val, bool):
                        val = "ON" if val else "OFF"
                    elif isinstance(val, list):
                        val = ", ".join(str(v) for v in val[:3])
                    cells.append(str(val))
                lines.append("| " + " | ".join(cells) + " |")
        else:
            lines.append("(none)")
        lines.append("")

    # Summary line at top (insert after header)
    overview = " | ".join(summary_parts)
    lines.insert(3, f"**Overview:** {overview}")
    lines.insert(4, "")

    report_content = "\n".join(lines)
    atomic_write(CONFIG_REPORT, report_content)

    log.info(f"Report generated: {len(lines)} lines, {overview}")
    print(f"Report written to {CONFIG_REPORT}")
    print(f"Overview: {overview}")
    return CONFIG_REPORT


if __name__ == "__main__":
    run()
