#!/usr/bin/env node
/**
 * @hook mcp-autostart
 * @event SessionStart
 * @matcher *
 * @description Auto-starts MCP servers defined in project's .mcp.json on session
 *   start. Reads the mcpServers object from .mcp.json in the current working
 *   directory and starts each server using mcpm. This ensures project-specific
 *   MCP tools are available immediately without manual intervention. Outputs a
 *   system reminder listing which servers were started.
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

let input = '';
try { input = fs.readFileSync(0, 'utf-8'); } catch (e) { process.exit(0); }

let data;
try { data = JSON.parse(input); } catch (e) { process.exit(0); }

const cwd = data.cwd || process.cwd();
const mcpConfigPath = path.join(cwd, '.mcp.json');

if (!fs.existsSync(mcpConfigPath)) {
  process.exit(0);
}

let mcpConfig;
try {
  mcpConfig = JSON.parse(fs.readFileSync(mcpConfigPath, 'utf8'));
} catch (e) {
  process.exit(0);
}

const servers = Object.keys(mcpConfig.mcpServers || {});
if (servers.length === 0) {
  process.exit(0);
}

const started = [];
for (const server of servers) {
  try {
    execSync(`node "/opt/mcp/mcp-manager/dist/cli.js" start ${server}`, {
      timeout: 30000,
      stdio: ['pipe', 'pipe', 'pipe']
    });
    started.push(server);
  } catch (e) {}
}

if (started.length > 0) {
  console.log(`<system-reminder>MCP servers auto-started: ${started.join(', ')}</system-reminder>`);
}

process.exit(0);
