# Global Preferences

- No emojis -- ASCII only
- No agents (Task tool) -- do work directly
- Never use Read tool on OneDrive paths -- use cat/head/tail via Bash
- Write/Edit/Grep/Glob tools are fine everywhere
- Git Bash shell -- use Unix paths, never PowerShell
- Never use temp dirs -- use project .tmp/ subfolder
- Secrets in OS credential store, never plaintext .env -- use credential-manager skill
- Test before saying done
- Fix problems on sight, don't ask permission
- Don't restate instructions as questions


## Tool Routing (managed by super-manager)

| Task | Use Skill |
|------|-----------|
| Hooks (add/remove/enable/debug) | hook-manager |
| Rules (add/remove/match) | rule-manager |
| MCP servers (start/stop/reload) | mcp-manager |
| Skills (scan/enrich/inventory) | skill-manager |
| Credentials (store/verify/audit) | credential-manager |
| Config overview (status/doctor) | super-manager |

## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array

<!-- mcp-manager-rules -->
## MCP Server Rules (auto-added by mcp-manager setup)

- All MCP servers managed by mcpm -- NEVER run `claude mcp add`, `mcpm` in Bash, or edit .mcp.json directly
- Use ONE tool: `mcp__mcp-manager__mcpm(operation="...")` -- no other tool names exist
- Add servers to mcpm's `servers.yaml` (mcp-manager repo dir), then `/mcp` -> Reconnect -> reload
- Store tokens via credential-manager (OS credential store), NEVER in config files
- MCP servers live in `ProjectsCL/MCP/` or `~/mcp/`
<!-- mcp-manager-rules -->


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array
