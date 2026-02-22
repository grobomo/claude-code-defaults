"""
output_formatter.py - Tables, trees, and dashboards for terminal output.

Formats data into readable terminal output. No emojis (per project rules).
Uses plain text indicators: OK, WARN, ERROR, OFF.
"""


def table(headers, rows):
    """
    Format data as a text table.
    headers: ["Name", "Status", "Description"]
    rows: [["hook-1", "OK", "Does stuff"], ...]
    """
    if not rows:
        return "(empty)"
    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    # Header
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    separator = "  ".join("-" * w for w in widths)
    # Rows
    lines = [header_line, separator]
    for row in rows:
        lines.append("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))
    return "\n".join(lines)


def status_line(manager_name, total, healthy, issues):
    """Format a single manager's status: 'Hook Manager     11 registered    11 healthy    0 issues'"""
    name = f"{manager_name}".ljust(25)
    return f"{name}{total:>3} registered  {healthy:>3} healthy  {issues:>3} issues"


def dashboard(manager_stats):
    """
    Format a full dashboard from all managers.
    manager_stats: [{"name": "Hook Manager", "total": 11, "healthy": 11, "issues": 0}, ...]
    """
    lines = ["", "Super Manager Status", "=" * 60, ""]
    for stat in manager_stats:
        lines.append(status_line(
            stat["name"], stat["total"], stat["healthy"], stat["issues"]
        ))
    lines.append("")
    return "\n".join(lines)


def item_list(items, columns):
    """
    Format a list of dicts as a table, picking specific columns.
    items: [{"name": "foo", "enabled": True, ...}, ...]
    columns: [("name", "Name"), ("enabled", "Status")]
    """
    headers = [col[1] for col in columns]
    rows = []
    for item in items:
        row = []
        for key, _ in columns:
            val = item.get(key, "")
            if isinstance(val, bool):
                val = "ON" if val else "OFF"
            elif isinstance(val, list):
                val = ", ".join(str(v) for v in val[:3])
                if len(item.get(key, [])) > 3:
                    val += "..."
            row.append(str(val))
        rows.append(row)
    return table(headers, rows)
