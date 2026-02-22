"""
configuration_paths.py - Every file and folder path the super-manager needs.

All paths are centralized here so no other file has magic strings.
Import paths from here: from shared.configuration_paths import HOOKS_DIR, SETTINGS_JSON, etc.
"""
import os

# Base directories
HOME = os.environ.get("HOME") or os.environ.get("USERPROFILE", "")
CLAUDE_DIR = os.path.join(HOME, ".claude")
SUPER_MANAGER_DIR = os.path.join(CLAUDE_DIR, "super-manager")

# Super-manager subdirectories
REGISTRIES_DIR = os.path.join(SUPER_MANAGER_DIR, "registries")
INSTRUCTIONS_BASE = os.path.join(CLAUDE_DIR, "instructions")
INSTRUCTIONS_DIR = INSTRUCTIONS_BASE  # base dir containing event subdirs (UserPromptSubmit/, Stop/)
INSTRUCTIONS_BACKUP_DIR = os.path.join(INSTRUCTIONS_BASE, "backups")
INSTRUCTIONS_REPOS_DIR = os.path.join(INSTRUCTIONS_BASE, "repos")
INSTRUCTIONS_REPOS_CONFIG = os.path.join(INSTRUCTIONS_BASE, "repos.json")
LOGS_DIR = os.path.join(SUPER_MANAGER_DIR, "logs")
REPORTS_DIR = os.path.join(SUPER_MANAGER_DIR, "reports")
ARCHIVE_DIR = os.path.join(SUPER_MANAGER_DIR, "archive")
TESTS_DIR = os.path.join(SUPER_MANAGER_DIR, "tests")
CREDENTIALS_DIR = os.path.join(SUPER_MANAGER_DIR, "credentials")

# Config sync directories (config import/export/uninstall)
CONFIG_DIR = os.path.join(SUPER_MANAGER_DIR, "config")
CONFIG_REPOS_DIR = os.path.join(CONFIG_DIR, "repos")
CONFIG_BACKUPS_DIR = os.path.join(CONFIG_DIR, "backups")

# Config sync state files
CONFIG_REPOS_JSON = os.path.join(CONFIG_DIR, "repos.json")
CONFIG_INSTALLED_JSON = os.path.join(CONFIG_DIR, "installed.json")
CONFIG_PENDING_JSON = os.path.join(CONFIG_DIR, "pending.json")

# Default config repo (bootstrap -- only hardcoded value in the system)
DEFAULT_CONFIG_REPO = "grobomo/claude-code-defaults"

# Registry files (inside super-manager)
HOOK_REGISTRY = os.path.join(REGISTRIES_DIR, "hook-registry.json")
SKILL_REGISTRY = os.path.join(REGISTRIES_DIR, "skill-registry.json")
CONFIG_HASH_FILE = os.path.join(REGISTRIES_DIR, "last-known-config-hash.txt")
CREDENTIAL_REGISTRY = os.path.join(CREDENTIALS_DIR, "credential-registry.json")

# Report file
CONFIG_REPORT = os.path.join(REPORTS_DIR, "config-report.md")

# Claude Code's own settings (NOT inside super-manager - stays in ~/.claude/)
SETTINGS_JSON = os.path.join(CLAUDE_DIR, "settings.json")

# Hook scripts directory (stays in ~/.claude/hooks/ - Claude Code reads from here)
HOOKS_DIR = os.path.join(CLAUDE_DIR, "hooks")

# Skill directories (Claude Code discovers skills here)
GLOBAL_SKILLS_DIR = os.path.join(CLAUDE_DIR, "skills")

# MCP servers.yaml (search order: env override, common locations, local fallback)
MCP_SERVERS_YAML_PATHS = [
    os.environ.get("MCP_SERVERS_YAML", ""),
    os.path.join(HOME, "mcp", "mcp-manager", "servers.yaml"),
    os.path.join(REGISTRIES_DIR, "servers.yaml"),
]
MCP_SERVERS_YAML_PATHS = [p for p in MCP_SERVERS_YAML_PATHS if p]

# Existing tools (originals, not touched)
SKILL_MGR_CLI = os.path.join(GLOBAL_SKILLS_DIR, "skill-marketplace", "cli", "skill-mgr")

# Valid Claude Code hook events
VALID_HOOK_EVENTS = [
    "SessionStart", "SessionEnd", "UserPromptSubmit",
    "PreToolUse", "PostToolUse", "PreCompact",
    "Stop", "SubAgentSop", "PermissionRequest",
]

def find_servers_yaml():
    """Find the first existing servers.yaml path."""
    for path in MCP_SERVERS_YAML_PATHS:
        if os.path.exists(path):
            return path
    return None

# Known .env file locations for credential scanning
# Each tuple: (service_name, env_file_path)
# Override: set MCP_DIR env var to your MCP servers root directory
_MCP_DIR = os.environ.get("MCP_DIR", os.path.join(HOME, "mcp"))
KNOWN_ENV_FILES = [
    # Add your MCP server .env paths here, e.g.:
    # ("wiki-lite", os.path.join(_MCP_DIR, "mcp-wiki-lite", ".env")),
    # ("jira-lite", os.path.join(_MCP_DIR, "mcp-jira-lite", ".env")),
]

# Patterns that indicate a value is a secret (not a URL, username, etc.)
SECRET_PATTERNS = [
    "TOKEN", "KEY", "SECRET", "PASSWORD", "PASS", "AUTH",
]
