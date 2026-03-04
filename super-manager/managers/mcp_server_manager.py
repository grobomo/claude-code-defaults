"""
mcp_server_manager.py - Config-only manager for MCP servers.

Reads/writes servers.yaml for configuration (add, remove, enable, disable).
Server lifecycle (start/stop/reload) is handled by mcpm.
"""
import sys
import os
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.configuration_paths import find_servers_yaml, SUPER_MANAGER_DIR
from shared.logger import create_logger
from shared.config_file_handler import read_yaml_servers
from shared.file_operations import archive_file

log = create_logger("mcp-server-manager")


def list_all():
    """List all MCP servers from servers.yaml."""
    yaml_path = find_servers_yaml()
    if not yaml_path:
        log.warn("servers.yaml not found in any known location")
        return {"items": [], "summary": "0 servers (servers.yaml not found)"}

    servers = read_yaml_servers(yaml_path)
    items = []
    for name, config in servers.items():
        items.append({
            "name": name,
            "enabled": config.get("enabled", False),
            "description": config.get("description", ""),
            "command": config.get("command", config.get("url", "")),
            "auto_start": config.get("auto_start", False),
            "tags": config.get("tags", []),
            "status": "enabled" if config.get("enabled", False) else "disabled",
        })

    enabled_count = sum(1 for i in items if i["enabled"])
    log.info("LIST: {} servers ({} enabled)".format(len(items), enabled_count))
    return {
        "items": items,
        "summary": "{} servers ({} enabled)".format(len(items), enabled_count),
    }


def add_item(name, command="", description="", args=None, tags=None, enabled=False):
    """Add a server to servers.yaml."""
    yaml_path = find_servers_yaml()
    if not yaml_path:
        return {"success": False, "message": "servers.yaml not found"}

    if not command:
        return {"success": False, "message": "command is required"}

    servers = read_yaml_servers(yaml_path)
    if name in servers:
        return {"success": False, "message": "Server '{}' already exists".format(name)}

    # Append to servers.yaml
    entry_lines = [
        "",
        "  {}:".format(name),
        '    description: "{}"'.format(description),
        '    command: "{}"'.format(command),
    ]
    if args:
        args_str = ", ".join('"{}"'.format(a) for a in args)
        entry_lines.append("    args: [{}]".format(args_str))
    if tags:
        tags_str = ", ".join('"{}"'.format(t) for t in tags)
        entry_lines.append("    tags: [{}]".format(tags_str))
    entry_lines.append("    enabled: {}".format("true" if enabled else "false"))

    with open(yaml_path, "a", encoding="utf-8") as f:
        f.write("\n".join(entry_lines) + "\n")

    log.info("ADD: {} -> {}".format(name, command))
    return {"success": True, "message": "Added server '{}'".format(name)}


def remove_item(name):
    """Remove a server from servers.yaml."""
    yaml_path = find_servers_yaml()
    if not yaml_path:
        return {"success": False, "message": "servers.yaml not found"}

    with open(yaml_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    skip = False
    found = False
    for line in lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())

        if indent == 2 and stripped.endswith(":") and not stripped.startswith("#"):
            server_name = stripped[:-1].strip()
            if server_name == name:
                skip = True
                found = True
                continue
            else:
                skip = False

        if skip and indent > 2:
            continue
        elif skip and indent <= 2:
            skip = False

        if not skip:
            new_lines.append(line)

    if not found:
        return {"success": False, "message": "Server '{}' not found".format(name)}

    with open(yaml_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    log.info("REMOVE: {}".format(name))
    return {"success": True, "message": "Removed server '{}' from servers.yaml".format(name)}


def enable_item(name):
    """Enable a server in servers.yaml."""
    yaml_path = find_servers_yaml()
    if not yaml_path:
        return {"success": False, "message": "servers.yaml not found"}
    return _set_enabled(yaml_path, name, True)


def disable_item(name):
    """Disable a server in servers.yaml."""
    yaml_path = find_servers_yaml()
    if not yaml_path:
        return {"success": False, "message": "servers.yaml not found"}
    return _set_enabled(yaml_path, name, False)


def _set_enabled(yaml_path, name, enabled):
    """Toggle enabled flag for a server in servers.yaml (in-place edit)."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    found_server = False
    in_target = False
    modified = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())

        if indent == 2 and stripped.endswith(":") and " " not in stripped:
            server_name = stripped[:-1]
            in_target = (server_name == name)
            if in_target:
                found_server = True
            continue

        if in_target and stripped.startswith("enabled:"):
            old_value = "true" if "true" in stripped else "false"
            new_value = "true" if enabled else "false"
            if old_value != new_value:
                lines[i] = line.replace("enabled: {}".format(old_value), "enabled: {}".format(new_value))
                modified = True
            break

    if not found_server:
        log.error("ENABLE/DISABLE: server '{}' not found in servers.yaml".format(name))
        return {"success": False, "message": "Server '{}' not found".format(name)}

    if modified:
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        action = "ENABLE" if enabled else "DISABLE"
        log.info("{}: {}".format(action, name))
        return {"success": True, "message": "Server '{}' {}".format(name, "enabled" if enabled else "disabled")}
    else:
        state = "enabled" if enabled else "disabled"
        return {"success": True, "message": "Server '{}' already {}".format(name, state)}


def verify_all(name=None):
    """Check MCP servers for issues."""
    yaml_path = find_servers_yaml()
    if not yaml_path:
        return {"healthy": [], "issues": [{"item": "servers.yaml", "problem": "servers.yaml not found", "fix": "Check MCP_SERVERS_YAML_PATHS"}]}

    servers = read_yaml_servers(yaml_path)
    issues = []

    for srv_name, config in servers.items():
        if name and srv_name != name:
            continue

        if config.get("enabled") and config.get("command"):
            cmd = config["command"]
            try:
                result = subprocess.run(
                    ["which", cmd], capture_output=True, text=True, timeout=5
                )
                if result.returncode != 0:
                    issues.append({
                        "item": srv_name,
                        "problem": "command '{}' not found on PATH".format(cmd),
                        "fix": "Check binary installation",
                    })
            except Exception:
                pass

        if not config.get("command") and not config.get("url"):
            issues.append({
                "item": srv_name,
                "problem": "no command or url configured",
                "fix": "Add command to servers.yaml",
            })

    healthy_list = [s for s in servers.keys() if not any(i.get("item") == s for i in issues)]
    log.info("VERIFY: {} servers checked, {} issues".format(len(servers), len(issues)))
    return {"healthy": healthy_list, "issues": issues}
