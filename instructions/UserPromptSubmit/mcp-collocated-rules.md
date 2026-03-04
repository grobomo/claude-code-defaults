---
id: mcp-collocated-rules
name: MCP-Collocated Rules Architecture
keywords: [mcp, rules, collocated, portable, migrate]
description: "WHY: Rules were scattered in personal dirs, disconnected from the MCP servers they describe. Moving rules INTO MCP server dirs makes them portable -- when an MCP migrates to a new Claude, its rules go with it."
enabled: true
priority: 5
action: Rules live WITH their MCP servers in rules/ subdirs
min_matches: 2
---

# MCP-Collocated Rules Architecture

## WHY

Rules about how to use an MCP server should live WITH that server, not in a central
personal rules directory. This makes rules portable -- when you install an MCP server
on a new machine, its rules migrate automatically.

## How It Works

1. Each MCP server directory can have a `rules/` subdirectory
2. Rule .md files in `rules/` use the same frontmatter format as personal rules
3. The rule loader (`sm-userpromptsubmit.js`) scans both:
   - `~/.claude/rules/UserPromptSubmit/` (personal rules)
   - `ProjectsCL/MCP/mcp-*/rules/` (MCP-collocated rules)
4. Keyword matching works identically for both locations

## Current Layout

```
ProjectsCL/MCP/
  mcp-blueprint-fork/rules/
    blueprint-health-check.md    # Recovery playbook for Blueprint issues
    browser-automation-routing.md # How to use Blueprint for web automation
    browser-via-blueprint.md      # Open URLs via Blueprint, never manually
    v1-page-recipes.md           # V1 console page init scripts and selectors
  mcp-manager/rules/
    mcp-management.md            # mcpm usage rules and anti-patterns
    mcpm-reload-flow.md          # How to reload after config changes
    mcpm-only-in-mcp-json.md     # Only mcpm goes in .mcp.json
    mcp-manager-routing.md       # Route MCP tasks to mcp-manager skill
  mcp-wiki-lite/rules/
    wiki-api-routing.md          # Route wiki tasks to wiki-api skill
  mcp-trend-docs/rules/
    trend-docs-routing.md        # Route docs tasks to trend-docs skill
```

## Rules That Stay Personal (no local MCP dir)

- `winremote-routing.md` (remote HTTP server, no local dir)
- `knowledge-mcp-routing.md` (remote HTTP server, no local dir)
- All non-MCP rules (formatting, bash, credentials, hooks, etc.)

## Adding Rules to an MCP Server

1. Create `rules/` dir in the MCP server's root
2. Write .md file with standard frontmatter (id, keywords, action, etc.)
3. Rule loader picks it up automatically on next prompt
