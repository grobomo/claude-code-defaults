"""
config_file_handler.py - Read and write JSON registries, YAML configs, and markdown frontmatter.

Handles the 3 config file formats used by super-manager:
  - JSON: hook-registry.json, skill-registry.json, settings.json
  - YAML: servers.yaml (simple parser, no PyYAML dependency)
  - Markdown frontmatter: instruction .md files (--- delimited YAML header)
"""
import json
import os


def read_json(file_path, default=None):
    """Read a JSON file. Returns default if file doesn't exist or is invalid."""
    if default is None:
        default = {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(file_path, data):
    """Write JSON atomically (temp file then rename)."""
    tmp_path = file_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp_path, file_path)


def _strip_yaml_quotes(value):
    """Strip surrounding quotes from a YAML value."""
    if len(value) >= 2:
        if (value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'"):
            return value[1:-1]
    return value


def read_yaml_servers(file_path):
    """
    Parse servers.yaml into a dict of server configs.
    Simple line-by-line parser - handles the specific format used by mcp-manager.
    Returns: {"server-name": {"description": "...", "enabled": True, "tags": [...], ...}, ...}
    """
    if not os.path.exists(file_path):
        return {}

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    servers = {}
    current = None
    current_list_key = None  # tracks which list we're inside (tags, args, keywords)

    for line in content.split("\n"):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())

        # Top-level server name (indent=2, ends with colon, no spaces in name)
        if indent == 2 and stripped.endswith(":") and " " not in stripped:
            current = stripped[:-1]
            servers[current] = {
                "description": "",
                "enabled": False,
                "auto_start": False,
                "command": "",
                "args": [],
                "tags": [],
                "keywords": [],
                "url": "",
            }
            current_list_key = None
            continue

        if current is None:
            continue

        # List item (- value)
        if stripped.startswith("- ") and current_list_key:
            value = _strip_yaml_quotes(stripped[2:].strip())
            servers[current][current_list_key].append(value)
            continue

        # Key: value pair
        if ":" in stripped and not stripped.startswith("-"):
            key = stripped.split(":")[0].strip()
            value = ":".join(stripped.split(":")[1:]).strip()
            current_list_key = None

            if key in ("tags", "args", "keywords"):
                current_list_key = key
                # Handle inline list: tags: [a, b]
                if value.startswith("[") and value.endswith("]"):
                    servers[current][key] = [_strip_yaml_quotes(v.strip()) for v in value[1:-1].split(",") if v.strip()]
                    current_list_key = None
            elif key == "enabled":
                servers[current]["enabled"] = _strip_yaml_quotes(value).lower() == "true"
            elif key == "auto_start":
                servers[current]["auto_start"] = _strip_yaml_quotes(value).lower() == "true"
            elif key in ("description", "command", "url"):
                servers[current][key] = _strip_yaml_quotes(value)
            elif key == "idle_timeout":
                servers[current]["idle_timeout"] = int(value) if value.isdigit() else 300000
            elif key == "startup_delay":
                servers[current]["startup_delay"] = int(value) if value.isdigit() else 3000

    return servers


def read_frontmatter(file_path):
    """
    Read a markdown file with YAML frontmatter.
    Returns: {"id": "...", "keywords": [...], "tools": [...], "description": "...", "body": "..."}
    Returns None if file doesn't exist or has no frontmatter.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return None

    if not content.startswith("---"):
        return None

    end_idx = content.index("---", 3) if "---" in content[3:] else -1
    if end_idx == -1:
        return None

    yaml_block = content[3:end_idx].strip()
    meta = {}

    for line in yaml_block.split("\n"):
        colon = line.find(":")
        if colon == -1:
            continue
        key = line[:colon].strip()
        value = line[colon + 1:].strip()
        # Parse lists: [a, b, c]
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key] = value

    meta["body"] = content[end_idx + 3:].strip()
    return meta


def write_frontmatter(file_path, meta, body):
    """Write a markdown file with YAML frontmatter."""
    lines = ["---"]
    for key, value in meta.items():
        if key == "body":
            continue
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(value)}]")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    content = "\n".join(lines) + "\n"

    tmp_path = file_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, file_path)
