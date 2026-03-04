#!/usr/bin/env python3
"""
inject_routing.py - Auto-inject Tool Routing table into ~/.claude/CLAUDE.md

Run after super-manager install to ensure Claude knows which skill handles
which config domain. Idempotent - safe to run multiple times.

WHY: Claude sees 30+ skills per prompt. Without an explicit routing table
in CLAUDE.md (re-injected every prompt by tool-reminder.js), Claude guesses
which skill to use and often picks the wrong one. The routing table is a
persistent lookup that's always visible, always correct.

Usage:
    python inject_routing.py          # inject/update routing table
    python inject_routing.py --check  # check if routing exists (exit 0/1)
    python inject_routing.py --remove # remove routing table
"""
import os
import sys
import tempfile

ROUTING_MARKER = "## Tool Routing (managed by super-manager)"

ROUTING_TABLE = """## Tool Routing (managed by super-manager)

| Task | Use Skill |
|------|-----------|
| Hooks (add/remove/enable/debug) | hook-manager |
| Rules (add/remove/match) | rule-manager |
| MCP servers (start/stop/reload) | mcp-manager |
| Skills (scan/enrich/inventory) | skill-manager |
| Credentials (store/verify/audit) | credential-manager |
| Config overview (status/doctor) | super-manager |"""

INSERT_BEFORE = "## Conditional Rules"


def get_claude_md_path():
    return os.path.join(os.path.expanduser("~"), ".claude", "CLAUDE.md")


def atomic_write(path, content):
    """Write to temp file then rename - prevents corruption on crash."""
    dirname = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dirname, suffix=".tmp", prefix=".claude-md-")
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        # Windows: can't rename over existing file, remove first
        if os.path.exists(path):
            os.replace(tmp_path, path)
        else:
            os.rename(tmp_path, path)
    except Exception:
        os.close(fd) if not os.get_inheritable(fd) else None
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def find_section(lines, marker):
    """Find start and end line indices of a ## section."""
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith(marker.strip()):
            start = i
            continue
        if start is not None and line.strip().startswith("## "):
            return start, i
    if start is not None:
        return start, len(lines)
    return None, None


def inject(claude_md_path):
    if not os.path.exists(claude_md_path):
        print(f"ERROR: {claude_md_path} not found")
        return False

    with open(claude_md_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")

    # Check if routing already exists
    start, end = find_section(lines, ROUTING_MARKER)

    if start is not None:
        # Replace existing section
        # Preserve trailing blank line before next section
        new_lines = lines[:start] + ROUTING_TABLE.split("\n")
        if end < len(lines) and lines[end].strip():
            new_lines.append("")
        new_lines += lines[end:]
        result = "\n".join(new_lines)
        atomic_write(claude_md_path, result)
        print(f"UPDATED Tool Routing in {claude_md_path}")
        return True

    # Insert before "## Conditional Rules" if it exists
    insert_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith(INSERT_BEFORE):
            insert_idx = i
            break

    if insert_idx is not None:
        new_lines = lines[:insert_idx] + ROUTING_TABLE.split("\n") + [""] + lines[insert_idx:]
    else:
        # Append at end
        new_lines = lines + [""] + ROUTING_TABLE.split("\n")

    result = "\n".join(new_lines)
    atomic_write(claude_md_path, result)
    print(f"INJECTED Tool Routing into {claude_md_path}")
    return True


def check(claude_md_path):
    if not os.path.exists(claude_md_path):
        return False
    with open(claude_md_path, "r", encoding="utf-8") as f:
        return ROUTING_MARKER in f.read()


def remove(claude_md_path):
    if not os.path.exists(claude_md_path):
        print(f"ERROR: {claude_md_path} not found")
        return False

    with open(claude_md_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    start, end = find_section(lines, ROUTING_MARKER)

    if start is None:
        print("Tool Routing section not found - nothing to remove")
        return True

    # Remove section and any blank line after
    if end < len(lines) and not lines[end].strip():
        end += 1
    new_lines = lines[:start] + lines[end:]
    result = "\n".join(new_lines)
    atomic_write(claude_md_path, result)
    print(f"REMOVED Tool Routing from {claude_md_path}")
    return True


def main():
    claude_md = get_claude_md_path()

    if "--check" in sys.argv:
        if check(claude_md):
            print("Tool Routing: present")
            sys.exit(0)
        else:
            print("Tool Routing: missing")
            sys.exit(1)

    if "--remove" in sys.argv:
        success = remove(claude_md)
        sys.exit(0 if success else 1)

    # Default: inject/update
    success = inject(claude_md)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
