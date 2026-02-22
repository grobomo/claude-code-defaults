# Global Claude Code Instructions

## Tool Routing (managed by super-manager)

| Task | Use |
|------|-----|
| Hooks (add/remove/enable/debug) | hook-manager skill |
| Instructions (add/remove/match) | instruction-manager skill |
| MCP servers (add/start/stop/reload) | mcp__mcp-manager__* tool calls (NOT Bash) |
| Skills (scan/enrich/inventory) | skill-manager skill |
| Credentials (store/verify/audit) | credential-manager skill |
| Config overview (status/doctor) | super-manager skill |

## Conditional Rules

Detailed rules for specific situations are in `~/.claude/instructions/UserPromptSubmit/*.md` and load automatically when keywords match your prompt. Before adding rules to this file, check if they belong in an instruction file instead. See: instruction-manager skill.

## Critical Rules

1. **Never clutter this file** -- conditional rules belong in instruction files or skill docs
2. **"When X do Y" patterns must be instructions** -- not written in CLAUDE.md
3. **Always fix bugs, never workaround** -- just fix it
4. **Skills preferred over MCP servers** -- use Skill tool first, MCP as fallback
5. **Never delete** -- always mv to archive/
