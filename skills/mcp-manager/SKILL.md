---
name: mcp-manager
description: "Manage MCP servers via mcp__mcp-manager__mcpm tool calls. NEVER run mcpm as a Bash command."
keywords:
  - mcp
  - server
  - servers
  - reload
  - yaml
  - mcpm
  - manage
---

# MCP Manager

## Rules

- **mcpm is an MCP server, NOT a CLI.** NEVER run `mcpm` in Bash. Always use MCP tool calls: `mcp__mcp-manager__mcpm`
- **Only mcp-manager goes in .mcp.json.** Never add direct server entries (`"type": "http"`, `"command": "python"`, etc.) -- all servers are registered in `servers.yaml` and proxied through mcp-manager
- **Never tell user to restart Claude Code** for MCP changes. Use the reload flow below instead
- MCP server source code lives in `ProjectsCL/MCP/` or `~/mcp/`

## .mcp.json Format (always)

```json
{
  "mcpServers": {
    "mcp-manager": {
      "command": "node",
      "args": ["path/to/mcp-manager/build/index.js"],
      "env": { ... },
      "servers": ["server1", "server2", ...]
    }
  }
}
```

No other top-level entries. Ever. If a server needs HTTP/SSE transport, build that into mcp-manager (proxy mode).

## Reload Flow (after config changes)

1. User runs `/mcp` -> select mcp-manager -> Reconnect
2. `mcp__mcp-manager__mcpm operation="reload"` (picks up servers.yaml changes)
3. `mcp__mcp-manager__mcpm operation="start" server="<name>"` (start any new servers)

## How to Call mcpm

All operations use ONE MCP tool: `mcp__mcp-manager__mcpm`
Pass the `operation` parameter plus any operation-specific params.

```
mcp__mcp-manager__mcpm  operation="list_servers"
mcp__mcp-manager__mcpm  operation="tools"  server="blueprint"
mcp__mcp-manager__mcpm  operation="start"  server="blueprint"
mcp__mcp-manager__mcpm  operation="call"   server="blueprint"  tool="navigate"  arguments='{"url":"https://example.com"}'
```

## Operations

| Category | Operation | Description |
|----------|-----------|-------------|
| **Query** | `list_servers` | Show all servers grouped by status |
| | `search` | Find servers/tools by keyword |
| | `details` | Full info on one server |
| | `tools` | List available tools (pass `server` for one server) |
| | `status` | System health + memory usage |
| | `help` | Show all operations |
| **Call** | `call` | Execute a tool on a backend server (auto-starts if needed) |
| **Admin** | `start` / `stop` / `restart` | Server lifecycle |
| | `enable` | Toggle server enabled/disabled |
| | `add` / `remove` | Register/unregister servers |
| | `reload` | Hot reload servers.yaml + .mcp.json |
| | `discover` | Scan for unregistered mcp-* folders |
| | `usage` | Which projects use which servers |
| | `ram` | Memory usage per server |

## Configuration Files

| File | Purpose |
|------|---------|
| `servers.yaml` | Central registry (all server definitions) |
| `.mcp.json` | Project server list (which servers this project uses) |
| `capabilities-cache.yaml` | Cached tool lists for stopped servers |

## Architecture

```
Claude Code  --(JSON-RPC stdio)-->  mcp-manager  --(spawn/JSON-RPC)-->  Backend Servers
                                         |
                                    Single "mcpm" tool
                                    with operation param

In-memory state:
  SERVERS   = all registered servers from servers.yaml
  RUNNING   = active server processes + metadata
  TOOLS     = tool arrays per running server
  TOOL_MAP  = tool_name -> server_name lookup

Idle checker: 60s interval, auto-stops servers idle > 5min (tag no_auto_stop to exempt)
```

super-manager does NOT manage MCP servers. It verifies mcpm exists and shows MCP counts in the status dashboard. All actual MCP operations are delegated to mcpm.

## Server Types

| Type | Config | How it connects |
|------|--------|----------------|
| **stdio** | `command` + `args` | Spawns child process, JSON-RPC over stdin/stdout |
| **HTTP** | `url` | POST JSON-RPC to URL, supports SSE responses |

## servers.yaml Format

```yaml
servers:
  my-server:
    command: python
    args: ["/path/to/server.py"]
    description: What it does
    enabled: true
    auto_start: false
    idle_timeout: 300000    # Stop after 5min idle (ms)
    startup_delay: 3000     # Wait before init (ms)
    tags: [api]
    keywords: [search, query]
    env:
      PYTHONIOENCODING: utf-8
defaults:
  timeout: 30000
  retry_count: 3
```

## Source Structure

```
mcp-manager/
├── src/
│   ├── index.ts              # Entry point, state, lifecycle
│   ├── types.ts              # TypeScript interfaces
│   ├── utils.ts              # Log sanitization (redacts keys/IPs)
│   ├── hooks.ts              # Post-tool hook system (optional)
│   ├── binary-filter.ts      # Image content -> temp files
│   └── operations/
│       ├── query/            # list, search, details, tools, status, help
│       ├── call/call.ts      # Tool proxy with auto-start
│       └── admin/            # lifecycle, registry, usage
├── build/index.js            # Compiled output (run this)
├── servers.yaml              # Server registry
├── docs/                     # Architecture diagrams and explainer
└── capabilities-cache.yaml   # Cached tool lists
```

## Troubleshooting: mcpm Tool Not Available

If the mcp-manager skill loads but you cannot call `mcp__mcp-manager__mcpm`, mcp-manager crashed on startup.

### Step 1: Verify the crash

Run manually to see the error:
```bash
cd "ProjectsCL/mcp/mcp-manager" && node build/index.js
```

### Step 2: Common crashes and fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `Dynamic require of "X" is not supported` | Node 24+ strict ESM breaks bundled CJS packages | Add package to `external` in `build.mjs`, then `node build.mjs` |
| `Cannot find module` | Missing dependency | `npm install` in mcp-manager dir |
| `EADDRINUSE` | Port conflict | Kill stale process or restart session |

### Step 3: Rebuild if needed

```bash
cd "ProjectsCL/mcp/mcp-manager" && node build.mjs
```

### Step 4: Reconnect WITHOUT restarting session

User runs `/mcp` in Claude Code CLI. This reconnects mcp-manager with the fixed build. No session restart needed.

### Step 5: Verify

```
mcp__mcp-manager__mcpm operation=list_servers
```

## Troubleshooting: v1-lite 403 AccessDenied

v1-lite uses credential-manager for API key. If you get 403:

1. Check credential exists: `python -c "import keyring; print(bool(keyring.get_password('claude-code', 'v1-lite/V1_API_KEY')))"`
2. Check .env has credential prefix: `V1_API_KEY=credential:v1-lite/V1_API_KEY`
3. After editing server.py, must restart via MCP tool calls: `mcp__mcp-manager__mcpm operation="stop" server="v1-lite"` then `mcp__mcp-manager__mcpm operation="start" server="v1-lite"`
