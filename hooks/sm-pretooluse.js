#!/usr/bin/env node
/**
 * @hook sm-pretooluse
 * @event PreToolUse
 * @matcher Bash|Edit|Write|Read|Glob|Grep|WebFetch|WebSearch|mcp__mcp-manager__mcpm
 * @description Super-manager PreToolUse entry point. Modules:
 *   1. enforcement-gate: hard-blocks auth URL misrouting, soft-warns others
 *   2. rule-guidelines-gate: injects RULE-GUIDELINES.md when editing rules/
 *   3. blueprint-rules-gate: injects Blueprint rules when calling blueprint via mcpm
 */
var fs = require('fs');
var path = require('path');

var HOME = process.env.HOME || process.env.USERPROFILE;
var LOG_FILE = path.join(HOME, '.claude', 'hooks', 'hooks.log');
var STATE_FILE = path.join(HOME, '.claude', 'super-manager', 'state', 'super-manager-pending-suggestions.json');
var ENFORCE_LOG = path.join(HOME, '.claude', 'super-manager', 'logs', 'super-manager-enforcement.log');
var STATUS_CACHE = path.join(HOME, '.claude', 'super-manager', 'state', 'status-line-cache.json');
var GUIDELINES_PATH = path.join(HOME, '.claude', 'rules', 'UserPromptSubmit', 'RULE-GUIDELINES.md');
var BLUEPRINT_RULES_PATH = path.join(HOME, '.claude', 'rules', 'UserPromptSubmit', 'blueprint-health-check.md');

function log(module, level, msg) {
  var ts = new Date().toISOString();
  try {
    fs.appendFileSync(LOG_FILE, ts + ' [' + level + '] [PreToolUse] [sm:' + module + '] ' + msg + '\n');
  } catch (e) {}
}

function updateStatusCache(enforcement) {
  try {
    var dir = path.dirname(STATUS_CACHE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    var existing = {};
    try { existing = JSON.parse(fs.readFileSync(STATUS_CACHE, 'utf-8')); } catch (e) {}
    existing.enforcement = enforcement;
    existing.enforcement_ts = new Date().toISOString();
    fs.writeFileSync(STATUS_CACHE, JSON.stringify(existing, null, 2));
  } catch (e) {
    log('enforcement', 'ERROR', 'status-line-cache write failed: ' + e.message);
  }
}

// ===== MODULE: enforcement-gate =====
// Hard-blocks WebFetch/WebSearch on authenticated URLs.
// Soft-warns (log-only) for other tool mismatches.

function moduleEnforcementGate(hookData) {
  var toolInput = hookData.tool_input || {};
  var toolName = hookData.tool_name || '';
  var filePath = toolInput.file_path || toolInput.command || '';

  // Skip enforcement for plan files, GSD artifacts, super-manager state
  if (filePath.indexOf('.claude/plans/') !== -1 || filePath.indexOf('.claude\\plans\\') !== -1 ||
      filePath.indexOf('.planning/') !== -1 || filePath.indexOf('.planning\\') !== -1 ||
      filePath.indexOf('status-line-cache') !== -1 ||
      filePath.indexOf('super-manager-pending-suggestions') !== -1 ||
      filePath.indexOf('super-manager-enforcement') !== -1 ||
      filePath.indexOf('super-manager/state/') !== -1 ||
      filePath.indexOf('super-manager/logs/') !== -1) {
    log('enforcement', 'DEBUG', 'skipped - meta artifact');
    return null;
  }

  // Always-on 2-line reminder
  console.log('Super-manager has sub-managers for hooks, rules, MCP, skills, and credentials. Use the matching skill instead of raw Bash/Edit/Write when managing Claude Code config.');

  // Read pending suggestions
  var state;
  try {
    if (!fs.existsSync(STATE_FILE)) return null;
    state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
  } catch (e) { return null; }

  // Auto-expire after 10 minutes
  if (state.timestamp) {
    var age = Date.now() - new Date(state.timestamp).getTime();
    if (age > 10 * 60 * 1000) {
      log('enforcement', 'DEBUG', 'expired suggestions (' + Math.round(age / 1000) + 's old)');
      try { fs.unlinkSync(STATE_FILE); } catch (e) {}
      return null;
    }
  }

  // Check for unfulfilled suggestions
  var fulfilled = {};
  var fulfilledArr = state.fulfilled || [];
  for (var fi = 0; fi < fulfilledArr.length; fi++) fulfilled[fulfilledArr[fi]] = true;

  var unfulfilled = [];
  var skillSuggestions = (state.suggestions && state.suggestions.skills) || [];
  for (var si = 0; si < skillSuggestions.length; si++) {
    if (!fulfilled[skillSuggestions[si].id]) {
      unfulfilled.push({ type: 'Skill', id: skillSuggestions[si].id, reason: skillSuggestions[si].reason });
    }
  }
  var mcpSuggestions = (state.suggestions && state.suggestions.mcps) || [];
  for (var mi = 0; mi < mcpSuggestions.length; mi++) {
    if (!fulfilled[mcpSuggestions[mi].name]) {
      unfulfilled.push({ type: 'MCP', id: mcpSuggestions[mi].name, reason: mcpSuggestions[mi].reason });
    }
  }

  if (unfulfilled.length === 0) return null;

  // Check for authenticated URL misrouting
  var AUTHENTICATED_DOMAINS = [
    'atlassian.net', 'confluence', 'jira', 'trello.com',
    'portal.xdr.trendmicro.com', 'portal.trendmicro.com'
  ];
  var authUrlBlock = false;
  if (toolName === 'WebFetch' || toolName === 'WebSearch') {
    var url = (toolInput.url || toolInput.query || '').toLowerCase();
    for (var di = 0; di < AUTHENTICATED_DOMAINS.length; di++) {
      if (url.indexOf(AUTHENTICATED_DOMAINS[di]) !== -1) {
        authUrlBlock = true;
        break;
      }
    }
  }

  // Write enforcement state to status-line-cache
  var action = authUrlBlock ? 'HARD_BLOCK' : 'SOFT_WARN';
  updateStatusCache({ pending: unfulfilled.map(function(x) { return x.id; }), action: action, tool: toolName });

  // Log enforcement
  var ts = new Date().toISOString();
  var logAction = authUrlBlock ? 'HARD_BLOCKED' : 'SOFT_WARNED';
  var logLine = ts + ' ' + logAction + ' tool=' + toolName + ' unfulfilled=' + unfulfilled.map(function(x) { return x.id; }).join(',') + '\n';
  try {
    var logDir = path.dirname(ENFORCE_LOG);
    if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
    fs.appendFileSync(ENFORCE_LOG, logLine);
  } catch (e) {}

  if (authUrlBlock) {
    // HARD BLOCK
    var lines = ['BLOCKED: ' + toolName + ' will fail for this authenticated URL.'];
    lines.push('Use one of these matched tools instead:');
    var skillItems = unfulfilled.filter(function(u) { return u.type === 'Skill'; });
    var mcpItems = unfulfilled.filter(function(u) { return u.type === 'MCP'; });
    for (var si2 = 0; si2 < skillItems.length; si2++) {
      lines.push('  SKILL: ' + skillItems[si2].id + ' (invoke via Skill tool)');
    }
    for (var mi2 = 0; mi2 < mcpItems.length; mi2++) {
      lines.push('  MCP: ' + mcpItems[mi2].id + ' (invoke via mcp__mcp-manager tools)');
    }
    log('enforcement', 'INFO', 'HARD_BLOCK tool=' + toolName + ' auth_url_detected');
    process.stderr.write(lines.join('\n'));
    return 'BLOCK';
  } else {
    log('enforcement', 'INFO', 'SOFT_WARN tool=' + toolName + ' unfulfilled=' + unfulfilled.map(function(x) { return x.id; }).join(','));
    return null;
  }
}

// ===== MODULE: rule-guidelines-gate =====
// Injects RULE-GUIDELINES.md content when Write|Edit targets ~/.claude/rules/

function moduleRuleGuidelinesGate(hookData) {
  var toolName = hookData.tool_name || '';
  if (toolName !== 'Write' && toolName !== 'Edit') return;

  var filePath = (hookData.tool_input && hookData.tool_input.file_path) || '';
  var normalized = filePath.replace(/\\/g, '/').toLowerCase();

  // Only fire for files inside ~/.claude/rules/
  var rulesDir = path.join(HOME, '.claude', 'rules').replace(/\\/g, '/').toLowerCase();
  if (normalized.indexOf(rulesDir) === -1) return;

  // Don't fire when editing RULE-GUIDELINES itself (prevent loop)
  if (normalized.indexOf('rule-guidelines') !== -1) return;

  try {
    var content = fs.readFileSync(GUIDELINES_PATH, 'utf-8');
    var endIdx = content.indexOf('---', 3);
    var body = endIdx !== -1 ? content.substring(endIdx + 3).trim() : content;
    console.log('RULE-GUIDELINES: Follow these when writing rule files.\n' + body);
    log('guidelines', 'INFO', 'injected for ' + path.basename(filePath));
  } catch (e) {
    // Guidelines file missing, skip
  }
}

// ===== MODULE: blueprint-rules-gate =====
// Injects blueprint-health-check.md when calling blueprint via mcpm

function moduleBlueprintRulesGate(hookData) {
  var toolName = hookData.tool_name || '';
  if (toolName !== 'mcp__mcp-manager__mcpm') return;

  var toolInput = hookData.tool_input || {};
  var server = (toolInput.server || '').toLowerCase();
  if (server !== 'blueprint') return;

  try {
    var content = fs.readFileSync(BLUEPRINT_RULES_PATH, 'utf-8');
    var endIdx = content.indexOf('---', 3);
    var body = endIdx !== -1 ? content.substring(endIdx + 3).trim() : content;
    console.log('BLUEPRINT RULES (auto-injected):\n' + body);
    log('blueprint', 'INFO', 'injected rules for blueprint call op=' + (toolInput.operation || ''));
  } catch (e) {
    // Blueprint rules file missing, skip
  }
}

// ===== MAIN =====

async function main() {
  var input = '';
  for await (var chunk of process.stdin) input += chunk;

  var hookData;
  try { hookData = JSON.parse(input); } catch (e) { process.exit(0); }

  // Module 1: rule-guidelines-gate (always runs, just injects context)
  moduleRuleGuidelinesGate(hookData);

  // Module 2: blueprint-rules-gate (injects rules when calling blueprint)
  moduleBlueprintRulesGate(hookData);

  // Module 3: enforcement-gate (may block)
  var result = moduleEnforcementGate(hookData);
  if (result === 'BLOCK') {
    process.exit(2);
  }

  process.exit(0);
}

main().catch(function() { process.exit(0); });
