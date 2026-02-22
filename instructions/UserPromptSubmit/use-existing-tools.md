---
id: use-existing-tools
name: Use Existing Tools First
keywords: [create, add, make, build, remember, rule, hook, new, install, setup, configure, write]
enabled: true
priority: 99
---
# STOP: Check Existing Tools First

## WHY This Exists

Claude's training defaults to building from scratch (create hooks, write files, edit CLAUDE.md). But the super-manager ecosystem already handles most configuration tasks. Building new things when tools already exist wastes time and frustrates the user.

## Before Creating Anything, Do This

1. **Read the Tool Routing table in CLAUDE.md** -- it maps tasks to skills
2. **Invoke the relevant skill** to understand what it already does
3. **Only build something new if no existing tool covers it**

## Key Principles

- **Persistent rules → instruction-manager** (NEVER a hook, NEVER CLAUDE.md)
- **"When X do Y" → instruction file** (NEVER a hook, NEVER CLAUDE.md)
- **Config management → super-manager ecosystem** (see `~/.claude/skills/super-manager/SKILL.md` for full capabilities)
- **Hook/skill/MCP/instruction CRUD → use the matching sub-manager skill**

## Where to Find What Exists

| Need to know... | Read... |
|-----------------|---------|
| Full ecosystem overview | `~/.claude/skills/super-manager/SKILL.md` |
| Hook management | `~/.claude/skills/hook-manager/SKILL.md` |
| Instruction management | `~/.claude/skills/instruction-manager/SKILL.md` |
| Skill management | `~/.claude/skills/skill-manager/SKILL.md` |
| Credential management | `~/.claude/skills/credential-manager/SKILL.md` |
| MCP server management | `~/.claude/skills/mcp-manager/SKILL.md` |
| Marketplace publishing | `~/.claude/skills/marketplace-manager/SKILL.md` |

**Read the relevant SKILL.md BEFORE deciding to build something new.**
