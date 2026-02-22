#!/usr/bin/env node
/**
 * MCP Manager Setup
 * Installs instruction files for MCP server management in Claude Code.
 * Uses shared setup-utils.js for backup, instruction install, and summary.
 *
 * Dependency chain:
 *   instruction-manager installed? -> write instruction .md files (preferred)
 *   instruction-manager missing?   -> inject rules into CLAUDE.md (fallback)
 *
 * Usage:
 *   node setup.js            # Install instructions + routing + backup
 *   node setup.js --uninstall # Restore from backup
 */

var utils = require('../../super-manager/shared/setup-utils');
var fs = require('fs');
var path = require('path');
var os = require('os');

var MANAGER_NAME = 'mcp-manager';
var CLAUDE_MD = path.join(os.homedir(), '.claude', 'CLAUDE.md');

// ================================================================
// Instruction content (kept in sync with on-disk .md files)
// ================================================================

var INSTRUCTION_MCP_MANAGEMENT = [
  '---',
  'id: mcp-management',
  'name: MCP Management',
  'keywords: [mcp, server, start, stop, add, tool, mcpm, install, clone, remote, http]',
  'enabled: true',
  'priority: 20',
  'description: MCP server management rules',
  '---',
  '',
  '# MCP Management Instructions',
  '',
  '## WHY',
  'All MCP servers are managed by mcpm (mcp-manager). This keeps a single source of truth in servers.yaml, avoids config sprawl, and prevents tokens from leaking into plaintext config files like .claude.json.',
  '',
  '## Rules',
  '',
  '1. **Always use MCP tool calls** (mcp__mcp-manager__*) for all MCP tasks - NEVER run "mcpm" as a Bash command',
  '2. "mcpm" is an MCP server, not a CLI. Use tools like: mcp__mcp-manager__reload, mcp__mcp-manager__start, mcp__mcp-manager__call',
  '3. **Never tell user to restart Claude** to load MCP servers - use mcp__mcp-manager__reload',
  '4. MCP servers are in `ProjectsCL/MCP/` or `~/mcp/`',
  '',
  '## NEVER Do These',
  '',
  '- **NEVER run `claude mcp add`** or `claude mcp add-json` -- this writes directly to .claude.json, bypassing mcpm',
  '- **NEVER add entries to .mcp.json** except mcp-manager itself',
  '- **NEVER put tokens/secrets in config files** -- use credential-manager to store in OS credential store',
  '- **NEVER run `mcpm` as a Bash command** -- it is an MCP server, not a CLI',
  '',
  '## Adding a New MCP Server',
  '',
  '1. Add server config to `~/.claude/super-manager/mcp/servers.yaml`',
  '2. Store any tokens via credential-manager (OS credential store)',
  '3. `/mcp` -> select mcp-manager -> Reconnect',
  '4. Call `mcp__mcp-manager__reload` to pick up servers.yaml changes',
  '5. Call `mcp__mcp-manager__start` with the server name'
].join('\n');

var INSTRUCTION_MCPM_ONLY_IN_MCP_JSON = [
  '---',
  'id: mcpm-only-in-mcp-json',
  'name: Only mcpm in .mcp.json',
  'keywords: [mcp, json, server, add, winremote, remote, http, configure, mcpm]',
  'enabled: true',
  '---',
  '',
  '# Rule: Only mcpm in .mcp.json',
  '',
  '## WHY',
  '',
  'The user NEVER wants any MCP server entry in .mcp.json except mcp-manager (mcpm). All servers - local stdio, remote HTTP, SSE - must go through mcpm. This keeps a single source of truth and avoids config sprawl.',
  '',
  '## What To Do',
  '',
  '- **NEVER** add a direct MCP server entry to .mcp.json (no `"type": "http"`, no `"command": "python"`, etc.)',
  '- **NEVER** run `claude mcp add` or `claude mcp add-json` -- writes to .claude.json, exposes tokens in plaintext',
  '- **ALWAYS** add servers to servers.yaml and manage via mcpm MCP tool calls',
  '- If a server needs HTTP/SSE transport, build that capability into mcpm (proxy mode)',
  '- If mcpm can\'t handle a server type yet, extend mcpm - don\'t work around it',
  '',
  '## .mcp.json Format (always)',
  '',
  '```json',
  '{',
  '  "mcpServers": {',
  '    "mcp-manager": {',
  '      "command": "node",',
  '      "args": ["path/to/mcp-manager/build/index.js"],',
  '      "env": { ... },',
  '      "servers": ["server1", "server2", ...]',
  '    }',
  '  }',
  '}',
  '```',
  '',
  'No other top-level entries. Ever.'
].join('\n');

var INSTRUCTION_MCPM_RELOAD_FLOW = [
  '---',
  'id: mcpm-reload-flow',
  'name: mcpm Reload Flow',
  'keywords: [reload, restart, mcp, reconnect, config, changed, server, mcpm, working]',
  'enabled: true',
  '---',
  '',
  '# How to Reload mcpm After Config Changes',
  '',
  '## WHY',
  '',
  'When servers.yaml or .mcp.json changes, the running mcpm process has stale config. Users don\'t need to restart Claude Code - they just need to reconnect mcpm.',
  '',
  '## Reload Flow',
  '',
  'Tell the user to run `/mcp`, select `mcp-manager`, and click reconnect. This reloads the mcpm process with the latest build and config. Then the reload MCP tool picks up servers.yaml changes.',
  '',
  '**Steps:**',
  '1. `/mcp` -> select mcp-manager -> Reconnect',
  '2. Call MCP tool `mcp__mcp-manager__reload` (picks up servers.yaml changes)',
  '3. Call MCP tool `mcp__mcp-manager__start` with server name (start any new servers)',
  '',
  '**IMPORTANT:** "mcpm" is an MCP server, NOT a CLI binary. Never run `mcpm` in Bash. Always use MCP tool calls like `mcp__mcp-manager__reload`, `mcp__mcp-manager__start`, `mcp__mcp-manager__call`, etc.',
  '',
  '## NEVER',
  '',
  '- Never run `mcpm` as a Bash command - it\'s an MCP server, use MCP tool calls',
  '- Never run `claude mcp add` - bypasses mcpm, leaks tokens to .claude.json',
  '- Never tell the user to restart Claude Code for mcpm changes',
  '- Never add MCP servers directly to .mcp.json (only mcpm goes there)'
].join('\n');

// ================================================================
// CLAUDE.md fallback content (used when instruction-manager is missing)
// ================================================================

var CLAUDE_MD_FALLBACK_MARKER = '<!-- mcp-manager-rules -->';
var CLAUDE_MD_FALLBACK = [
  '',
  CLAUDE_MD_FALLBACK_MARKER,
  '## MCP Server Rules (auto-added by mcp-manager setup)',
  '',
  '- All MCP servers managed by mcpm -- NEVER run `claude mcp add`, `mcpm` in Bash, or edit .mcp.json directly',
  '- Use MCP tool calls: mcp__mcp-manager__reload, mcp__mcp-manager__start, mcp__mcp-manager__call',
  '- Add servers to `~/.claude/super-manager/mcp/servers.yaml`, then `/mcp` -> Reconnect -> reload',
  '- Store tokens via credential-manager (OS credential store), NEVER in config files',
  '- MCP servers live in `ProjectsCL/MCP/` or `~/mcp/`',
  CLAUDE_MD_FALLBACK_MARKER,
  ''
].join('\n');

// ================================================================
// Fallback: inject/remove rules from CLAUDE.md
// ================================================================

function injectClaudeMdFallback() {
  if (!fs.existsSync(CLAUDE_MD)) return false;
  var content = fs.readFileSync(CLAUDE_MD, 'utf8');
  if (content.indexOf(CLAUDE_MD_FALLBACK_MARKER) !== -1) return false; // already there
  fs.writeFileSync(CLAUDE_MD, content + CLAUDE_MD_FALLBACK, 'utf8');
  return true;
}

function removeClaudeMdFallback() {
  if (!fs.existsSync(CLAUDE_MD)) return false;
  var content = fs.readFileSync(CLAUDE_MD, 'utf8');
  var startIdx = content.indexOf(CLAUDE_MD_FALLBACK_MARKER);
  if (startIdx === -1) return false;
  var endIdx = content.indexOf(CLAUDE_MD_FALLBACK_MARKER, startIdx + 1);
  if (endIdx === -1) return false;
  var endOfMarker = endIdx + CLAUDE_MD_FALLBACK_MARKER.length;
  // Remove the fallback block (plus surrounding whitespace)
  var before = content.slice(0, startIdx).replace(/\n+$/, '\n');
  var after = content.slice(endOfMarker).replace(/^\n+/, '\n');
  fs.writeFileSync(CLAUDE_MD, before + after, 'utf8');
  return true;
}

// ================================================================
// Main
// ================================================================

function main() {
  console.log('[' + MANAGER_NAME + ':setup] Starting...');
  console.log('');

  // ----------------------------------------------------------
  // 1. Check dependencies
  // ----------------------------------------------------------
  var warnings = [];
  var imInstalled = utils.checkDependency('instruction-manager').installed;
  var hmInstalled = utils.checkDependency('hook-manager').installed;

  if (!imInstalled) {
    warnings.push('instruction-manager not installed. Injecting rules into CLAUDE.md as fallback.');
    warnings.push('Install instruction-manager for keyword-matched contextual injection.');
  }
  if (!hmInstalled) {
    warnings.push('hook-manager not installed. No hooks needed now, but recommended.');
  }

  // ----------------------------------------------------------
  // 2. Backup existing files before changes
  // ----------------------------------------------------------
  var filesToBackup = [
    utils.SETTINGS_JSON,
    CLAUDE_MD,
    path.join(utils.INSTRUCTIONS_DIR, 'UserPromptSubmit', 'mcp-management.md'),
    path.join(utils.INSTRUCTIONS_DIR, 'UserPromptSubmit', 'mcpm-only-in-mcp-json.md'),
    path.join(utils.INSTRUCTIONS_DIR, 'UserPromptSubmit', 'mcpm-reload-flow.md'),
    path.join(utils.INSTRUCTIONS_DIR, 'UserPromptSubmit', 'mcp-manager-routing.md')
  ];

  var backupResult = utils.backup(MANAGER_NAME, filesToBackup);
  console.log('[' + MANAGER_NAME + ':setup] Backup: ' + backupResult.backupDir);

  // ----------------------------------------------------------
  // 3. Install instructions (or fallback to CLAUDE.md)
  // ----------------------------------------------------------
  var instructions = [];

  if (imInstalled) {
    // Preferred: write instruction .md files (keyword-matched injection)
    removeClaudeMdFallback(); // clean up any old fallback

    var instList = [
      { id: 'mcp-management', content: INSTRUCTION_MCP_MANAGEMENT },
      { id: 'mcpm-only-in-mcp-json', content: INSTRUCTION_MCPM_ONLY_IN_MCP_JSON },
      { id: 'mcpm-reload-flow', content: INSTRUCTION_MCPM_RELOAD_FLOW }
    ];

    for (var i = 0; i < instList.length; i++) {
      var inst = utils.installInstruction({
        id: instList[i].id,
        content: instList[i].content,
        event: 'UserPromptSubmit'
      });
      instructions.push(inst);
      if (inst.method !== 'skipped') {
        utils.trackCreatedFile(backupResult.backupDir, inst.path);
      }
    }
  } else {
    // Fallback: inject condensed rules into CLAUDE.md
    var injected = injectClaudeMdFallback();
    instructions.push({
      method: injected ? 'claude-md-fallback' : 'skipped',
      path: CLAUDE_MD,
      fallback: true
    });
  }

  // ----------------------------------------------------------
  // 4. Create routing instruction (auto-route prompts to mcpm)
  // ----------------------------------------------------------
  var routing = utils.ensureRoutingInstruction({
    toolName: 'mcp-manager',
    toolType: 'skill',
    keywords: ['mcp', 'mcpm', 'mcp server', 'mcp install'],
    description: 'Manage MCP servers (add, start, stop, reload)',
    whenToUse: 'prompt involves installing, configuring, or managing MCP servers',
    neverUse: 'Bash with mcpm commands',
    whyNot: 'mcpm must only be called via mcp__mcp-manager__* tool calls',
    howToUse: 'Skill tool: mcp-manager add server-name'
  });
  instructions.push(routing);
  if (routing.method !== 'skipped') {
    utils.trackCreatedFile(backupResult.backupDir, routing.path);
  }

  // ----------------------------------------------------------
  // 5. Print summary
  // ----------------------------------------------------------
  utils.printSummary({
    manager: MANAGER_NAME,
    backup: backupResult,
    instructions: instructions,
    hooks: [],
    warnings: warnings
  });

  return {
    backup: backupResult,
    instructions: instructions,
    warnings: warnings
  };
}

// ================================================================
// Uninstall
// ================================================================

function uninstall() {
  console.log('[' + MANAGER_NAME + ':uninstall] Starting...');
  var latestBackup = utils.findLatestBackup(MANAGER_NAME);
  if (!latestBackup) {
    console.log('[' + MANAGER_NAME + ':uninstall] No backup found. Nothing to restore.');
    return;
  }
  var result = utils.restore(latestBackup);
  removeClaudeMdFallback(); // clean up fallback if present
  console.log('[' + MANAGER_NAME + ':uninstall] Restored ' + result.restored.length + ' files');
  console.log('[' + MANAGER_NAME + ':uninstall] Removed ' + result.removed.length + ' created files');
  if (result.errors.length > 0) {
    console.log('[' + MANAGER_NAME + ':uninstall] Errors: ' + result.errors.join(', '));
  }
}

module.exports = { main: main, uninstall: uninstall };
if (require.main === module) {
  if (process.argv.indexOf('--uninstall') !== -1) {
    uninstall();
  } else {
    main();
  }
}
