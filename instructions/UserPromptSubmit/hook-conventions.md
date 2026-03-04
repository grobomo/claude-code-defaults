---
id: hook-conventions
name: Hook Conventions
keywords: [hook, create, write, contract, stdin, event, PreToolUse, PostToolUse, settings, settings.json]
description: "WHY: Multiple hook entries per event in settings.json causes config sprawl and ordering bugs. WHAT: One sm hook per event -- add modules inside it, never add separate entries."
enabled: true
priority: 5
action: One sm hook per event -- add modules inside sm hooks
min_matches: 1
---

# Hook Conventions

## Architecture: One SM Hook Per Event

**settings.json has exactly ONE hook entry per event, and that hook is the super-manager (sm) hook.**

This is the same principle as mcpm in .mcp.json: one entry point that routes internally.

| Event | SM Hook | Modules Inside |
|-------|---------|----------------|
| UserPromptSubmit | sm-userpromptsubmit.js | skill suggestions, MCP suggestions, rule matching |
| PreToolUse | sm-pretooluse.js | enforcement-gate, rule-guidelines-gate |
| PostToolUse | sm-posttooluse.js | tool logging, verification |
| Stop | sm-stop.js | response checking |
| SessionStart | sm-sessionstart.js | config scan, report generation |

## Adding New Hook Logic

To add new hook behavior (e.g., Blueprint rule injection on PreToolUse):

1. **Open the existing sm hook** for that event (e.g., sm-pretooluse.js)
2. **Add a new module function** (e.g., `moduleBlueprintRules(hookData)`)
3. **Call it from main()** alongside existing modules
4. **Expand the matcher** if needed (e.g., add `mcp__mcp-manager__mcpm` to PreToolUse matcher)
5. **NEVER add a separate hook entry** to settings.json

## NEVER Do These

- **NEVER** add a new hook entry to settings.json -- add a module inside the sm hook
- **NEVER** edit settings.json directly -- use hook-manager skill
- **NEVER** create standalone hook .js files that get their own settings.json entry
- **NEVER** use async/await in hooks -- use var, fs.readFileSync, synchronous only
- **NEVER** skip the hook-manager skill -- it validates contracts and updates registries

## Hook Contracts

- stdin contract varies by event type -- check hook-manager SKILL.md
- Events WITHOUT matcher (UserPromptSubmit, Stop): OMIT matcher field
- Events WITH matcher (PreToolUse, PostToolUse): matcher is a pipe-separated string
- PreToolUse: exit 0 to allow (stdout = injected context), exit 2 to block
- Stop: output `{"decision":"block","reason":"..."}` to block, or exit 0 to allow
