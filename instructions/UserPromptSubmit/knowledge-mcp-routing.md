---
id: knowledge-mcp-routing
name: knowledge-mcp Routing
keywords: [knowledge base, KB article, support case, threat encyclopedia, digital vaccine, deep security kernel]
enabled: true
priority: 10
action: Use knowledge-mcp MCP server
min_matches: 1
---

# knowledge-mcp Routing

## WHY
Trend Micro Knowledge MCP Server - KB articles, product docs, support cases, threat intel. The knowledge-mcp MCP server is already configured
and authenticated. Using it is faster and more reliable than generic tools.

## Rule
When prompt asks about Trend Micro KB articles, support cases, threat encyclopedia, product knowledge base:

1. **Use knowledge-mcp MCP server** (preferred)
2. **Invoke via MCP tool calls**
3. **Fallback to trend-docs skill** if the MCP server fails


## How
```
MCP tool calls: mcp__knowledge-mcp__search or similar tools
```
