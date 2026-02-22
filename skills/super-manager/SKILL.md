---
name: super-manager
description: Unified manager for all Claude Code configuration - hooks, skills, MCP servers, and instructions. Discovers, registers, and enforces usage of all components.
---

# Super Manager

Unified configuration management and enforcement for Claude Code. Discovers and tracks all hooks, skills, MCP servers, and instructions. Enforces that matched tools are used before falling back to general tools.

## Quick Commands

```bash
# Discover and register everything in ~/.claude/
python ~/.claude/super-manager/super_manager.py discover

# Scan only, no changes
python ~/.claude/super-manager/super_manager.py discover --report

# Dashboard - health of all components
python ~/.claude/super-manager/super_manager.py status

# Doctor - find and fix issues
python ~/.claude/super-manager/super_manager.py doctor --fix

# Generate markdown report
python ~/.claude/super-manager/super_manager.py report
```

## Terminology

| Term | Meaning |
|------|---------|
| **Managed** | Actively used (in settings.json, enabled=true, etc.) |
| **Registered** | Tracked in registry but not actively managed |
| **Orphaned** | In registry but file missing from disk |

## Discovery

`discover` scans ~/.claude/ and auto-registers everything found:

- Hooks: cross-references disk files, settings.json, and hook-registry.json
- Skills: cross-references ~/.claude/skills/*/SKILL.md with skill-registry.json
- MCP Servers: reads servers.yaml (servers.yaml IS the registry)
- Instructions: scans .md files with frontmatter

## Enforcement

Two hooks enforce that Claude uses matched skills/MCPs before general tools:

- **super-manager-enforcement-gate** (PreToolUse): blocks Bash/Edit/Write if matched skill/MCP not yet invoked
- **super-manager-check-enforcement** (PostToolUse): marks suggestions fulfilled when Skill/Task tools used
- State: `state/super-manager-pending-suggestions.json`
- Log: `logs/super-manager-enforcement.log`

## Sub-Managers (5)

| Sub-Manager | Skill | Description |
|-------------|-------|-------------|
| hooks | [hook-manager](~/.claude/skills/hook-manager/) | Create, manage, validate hooks |
| skills | [skill-manager](~/.claude/skills/skill-manager/) | Scan, enrich keywords, track skills |
| mcp | [mcp-manager](~/.claude/skills/mcp-manager/) | Server config, start/stop/reload |
| instructions | [instruction-manager](~/.claude/skills/instruction-manager/) | Context-aware .md files with keyword matching |
| credentials | [credential-manager](~/.claude/skills/credential-manager/) | OS credential store for API tokens/secrets |

### Hooks
```bash
python ~/.claude/super-manager/super_manager.py hooks list|add|remove|enable|disable|verify
```

### Skills
```bash
python ~/.claude/super-manager/super_manager.py skills list|add|remove|enable|disable|verify
```

### MCP Servers (config-only, mcpm handles lifecycle)
```bash
python ~/.claude/super-manager/super_manager.py mcp list|enable|disable|verify
```

### Instructions
```bash
python ~/.claude/super-manager/super_manager.py instructions list|add|remove|enable|disable|verify|match
```

### Credentials
```bash
python ~/.claude/super-manager/super_manager.py credentials list|store|verify|audit|migrate
```

## Architecture

```
~/.claude/super-manager/
|-- super_manager.py          # CLI entry point
|-- SKILL.md                  # This file
|-- CLAUDE.md                 # Technical workflow for Claude
|-- README.md                 # Human overview
|
|-- hooks/                    # Hook registry metadata
|-- skills/                   # Skill registry metadata
|-- mcp/                      # Bundled mcpm + server configs
|-- instructions/             # Context-aware instruction .md files
|-- managers/                 # 4 sub-manager Python modules
|-- commands/                 # Orchestration: status, doctor, report, discover
|-- state/                    # Runtime state (enforcement pending suggestions)
|-- shared/                   # Shared Python modules
|-- registries/               # Combined registries
|-- logs/                     # Per-manager + enforcement logs
|-- reports/                  # Generated reports
+-- archive/                  # Archived items (never deleted)
```

## Key Principles

- **Discover everything** - all items in ~/.claude/ are tracked
- **Managed vs registered** - active items are managed, inactive are registered
- **Enforce tool usage** - PreToolUse hooks block bypassing matched skills/MCPs
- **Never delete, always archive** - removals go to archive/ with timestamp
- **Components stay in default locations** - hooks in ~/.claude/hooks/, skills in ~/.claude/skills/
- **Super-manager references, does not own** - registries point to canonical locations
