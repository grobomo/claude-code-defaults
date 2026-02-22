#!/usr/bin/env node
/**
 * @hook super-manager-enforcement-gate
 * @event PreToolUse
 * @matcher Bash|Edit|Write|Read|Glob|Grep|WebFetch|WebSearch
 * @description Scope-aware enforcement: hard-blocks tools touching scoped skill paths,
 *   soft-warns for non-scoped suggestions. Writes to status-line-cache.
 */
var fs = require('fs');
var path = require('path');

var HOME = process.env.HOME || process.env.USERPROFILE;
var LOG_FILE = path.join(HOME, '.claude', 'hooks', 'hooks.log');
var STATE_FILE = path.join(HOME, '.claude', 'super-manager', 'state', 'super-manager-pending-suggestions.json');
var ENFORCE_LOG = path.join(HOME, '.claude', 'super-manager', 'logs', 'super-manager-enforcement.log');
var REGISTRY_FILE = path.join(HOME, '.claude', 'hooks', 'skill-registry.json');
var STATUS_CACHE = path.join(HOME, '.claude', 'super-manager', 'state', 'status-line-cache.json');

function log(level, msg) {
  var ts = new Date().toISOString();
  try {
    fs.appendFileSync(LOG_FILE, ts + ' [' + level + '] [PreToolUse] [enforcement-gate] ' + msg + '\n');
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
    log('ERROR', 'status-line-cache write failed: ' + e.message);
  }
}

function extractTargetPaths(toolName, toolInput) {
  var paths = [];
  if ((toolName === 'Read' || toolName === 'Write' || toolName === 'Edit') && toolInput.file_path) {
    paths.push(toolInput.file_path);
  }
  if ((toolName === 'Glob' || toolName === 'Grep') && toolInput.path) {
    paths.push(toolInput.path);
  }
  if (toolName === 'Bash' && toolInput.command) {
    paths.push(toolInput.command);
  }
  return paths;
}

function pathMatchesScope(targetPath, scopePaths) {
  var normalized = targetPath.replace(/\\/g, '/').toLowerCase();
  for (var i = 0; i < scopePaths.length; i++) {
    var sp = scopePaths[i].replace(/\\/g, '/').toLowerCase();
    if (normalized.indexOf(sp) !== -1) return true;
  }
  return false;
}

function loadScopes() {
  try {
    var registry = JSON.parse(fs.readFileSync(REGISTRY_FILE, 'utf-8'));
    var scopes = {};
    var skills = registry.skills || [];
    for (var i = 0; i < skills.length; i++) {
      var skill = skills[i];
      if (skill.scope && skill.scope.paths && skill.scope.paths.length > 0) {
        scopes[skill.id] = skill.scope.paths;
      }
    }
    return scopes;
  } catch (e) {
    return {};
  }
}

async function main() {
  var input = '';
  for await (var chunk of process.stdin) input += chunk;

  var hookData;
  try { hookData = JSON.parse(input); } catch (e) { process.exit(0); }

  var toolInput = hookData.tool_input || {};
  var toolName = hookData.tool_name || '';
  var filePath = toolInput.file_path || toolInput.command || '';

  // Skip enforcement for plan files, GSD artifacts, and status-line-cache itself
  if (filePath.indexOf('.claude/plans/') !== -1 || filePath.indexOf('.claude\\plans\\') !== -1 ||
      filePath.indexOf('.planning/') !== -1 || filePath.indexOf('.planning\\') !== -1 ||
      filePath.indexOf('status-line-cache') !== -1 ||
      filePath.indexOf('super-manager-pending-suggestions') !== -1 ||
      filePath.indexOf('super-manager-enforcement') !== -1 ||
      filePath.indexOf('super-manager/state/') !== -1 ||
      filePath.indexOf('super-manager/logs/') !== -1) {
    log('DEBUG', 'skipped - plan/gsd/cache artifact');
    process.exit(0);
  }

  // Read pending suggestions
  var state;
  try {
    if (!fs.existsSync(STATE_FILE)) { process.exit(0); }
    state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
  } catch (e) { process.exit(0); }

  // Auto-expire after 10 minutes
  if (state.timestamp) {
    var age = Date.now() - new Date(state.timestamp).getTime();
    if (age > 10 * 60 * 1000) {
      log('DEBUG', 'expired suggestions (' + Math.round(age / 1000) + 's old)');
      try { fs.unlinkSync(STATE_FILE); } catch (e) {}
      process.exit(0);
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

  if (unfulfilled.length === 0) { process.exit(0); }

  // Load scopes from skill registry
  var scopes = loadScopes();
  var targetPaths = extractTargetPaths(toolName, toolInput);

  // Check for scope violations (hard block candidates)
  var scopeViolations = [];
  for (var ui = 0; ui < unfulfilled.length; ui++) {
    var u = unfulfilled[ui];
    if (u.type !== 'Skill') continue;
    var skillScopes = scopes[u.id];
    if (!skillScopes) continue;

    for (var ti = 0; ti < targetPaths.length; ti++) {
      if (pathMatchesScope(targetPaths[ti], skillScopes)) {
        scopeViolations.push({
          skill: u.id,
          reason: u.reason,
          scopePaths: skillScopes,
          target: targetPaths[ti].slice(0, 120)
        });
        break;
      }
    }
  }

  // Write enforcement state to status-line-cache
  var action = scopeViolations.length > 0 ? 'HARD_BLOCK' : 'SOFT_WARN';
  updateStatusCache({
    pending: unfulfilled.map(function(x) { return x.id; }),
    violations: scopeViolations.map(function(x) { return x.skill; }),
    action: action,
    tool: toolName
  });

  // Log enforcement
  var ts = new Date().toISOString();
  var logAction = scopeViolations.length > 0 ? 'HARD_BLOCKED' : 'SOFT_WARNED';
  var logLine = ts + ' ' + logAction + ' tool=' + toolName + ' unfulfilled=' + unfulfilled.map(function(x) { return x.id; }).join(',') + '\n';
  try {
    var logDir = path.dirname(ENFORCE_LOG);
    if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
    fs.appendFileSync(ENFORCE_LOG, logLine);
  } catch (e) {}

  // DECISION (2026-02-18): Log-only mode. No blocking, no warnings in output.
  // Native skill matching via frontmatter handles routing. This hook only logs
  // for skill usage analytics.
  log('INFO', action + ' (log-only) tool=' + toolName + ' unfulfilled=' + unfulfilled.map(function(x) { return x.id; }).join(','));
  process.exit(0);
}

main().catch(function() { process.exit(0); });
