#!/usr/bin/env node
/**
 * @hook sm-posttooluse
 * @event PostToolUse
 * @matcher Skill|Task
 * @description Super-manager PostToolUse entry point. Modules:
 *   1. fulfillment-tracker: marks suggestions as fulfilled when Skill/Task used
 *   2. usage-logger: logs all Skill/Task invocations to JSONL for analytics
 */
var fs = require('fs');
var path = require('path');

var HOME = process.env.HOME || process.env.USERPROFILE;
var LOG_FILE = path.join(HOME, '.claude', 'hooks', 'hooks.log');
var STATE_FILE = path.join(HOME, '.claude', 'super-manager', 'state', 'super-manager-pending-suggestions.json');
var SKILL_USAGE_LOG = path.join(HOME, '.claude', 'super-manager', 'logs', 'skill-usage.jsonl');

function log(module, level, msg) {
  var ts = new Date().toISOString();
  try {
    fs.appendFileSync(LOG_FILE, ts + ' [' + level + '] [PostToolUse] [sm:' + module + '] ' + msg + '\n');
  } catch (e) {}
}

// ===== MODULE: fulfillment-tracker =====
// Marks pending suggestions as fulfilled when the matching Skill/Task is used

function moduleFulfillmentTracker(invokedId) {
  var state;
  try {
    if (!fs.existsSync(STATE_FILE)) return;
    state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
  } catch (e) { return; }

  var fulfilled = {};
  var fulfilledArr = state.fulfilled || [];
  for (var fi = 0; fi < fulfilledArr.length; fi++) fulfilled[fulfilledArr[fi]] = true;

  var matched = false;
  var skills = (state.suggestions && state.suggestions.skills) || [];
  for (var si = 0; si < skills.length; si++) {
    if (skills[si].id === invokedId || invokedId.indexOf(skills[si].id) !== -1) {
      fulfilled[skills[si].id] = true;
      matched = true;
    }
  }
  var mcps = (state.suggestions && state.suggestions.mcps) || [];
  for (var mi = 0; mi < mcps.length; mi++) {
    if (mcps[mi].name === invokedId || invokedId.indexOf(mcps[mi].name) !== -1) {
      fulfilled[mcps[mi].name] = true;
      matched = true;
    }
  }

  if (matched) {
    state.fulfilled = Object.keys(fulfilled);
    try { fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2)); } catch (e) {}
    log('fulfillment', 'INFO', 'fulfilled: ' + invokedId);
  }
}

// ===== MODULE: usage-logger =====
// Logs every Skill/Task invocation to JSONL for analytics

function moduleUsageLogger(toolName, invokedId, promptSnippet) {
  var ts = new Date().toISOString();
  var entry = {
    timestamp: ts,
    tool: toolName,
    skill: invokedId,
    prompt_snippet: (promptSnippet || '').slice(0, 100)
  };
  try {
    var logDir = path.dirname(SKILL_USAGE_LOG);
    if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
    fs.appendFileSync(SKILL_USAGE_LOG, JSON.stringify(entry) + '\n');
  } catch (e) {}
  log('usage', 'DEBUG', 'logged: ' + toolName + '/' + invokedId);
}

// ===== MODULE: blueprint-action-logger =====
// Logs Blueprint browser_evaluate/browser_tabs calls for V1 recipe pattern discovery
var BLUEPRINT_ACTION_LOG = path.join(HOME, '.claude', 'hooks', 'data', 'v1-action-log.jsonl');

function moduleBlueprintLogger(toolName, toolInput, toolOutput) {
  // Only process mcpm calls that route to blueprint
  if (toolName !== 'mcp__mcp-manager__mcpm') return;
  var op = toolInput.operation || '';
  var server = toolInput.server || '';
  var tool = toolInput.tool || '';
  if (op !== 'call' || server !== 'blueprint') return;

  // Extract action summary based on Blueprint tool
  var summary = '';
  var args = toolInput.arguments || {};
  if (tool === 'browser_evaluate') {
    var script = (args.expression || args.script || '').substring(0, 200);
    summary = 'evaluate: ' + script;
  } else if (tool === 'browser_tabs') {
    summary = 'tabs: ' + (args.action || 'unknown');
    if (args.url) summary += ' url=' + args.url.substring(0, 80);
    if (args.index !== undefined) summary += ' index=' + args.index;
  } else if (tool === 'browser_interact') {
    summary = 'interact: ' + (args.action || 'click');
    if (args.text) summary += ' text=' + args.text.substring(0, 40);
  } else if (tool === 'browser_take_screenshot') {
    summary = 'screenshot';
  } else if (tool === 'browser_snapshot') {
    summary = 'snapshot';
  } else {
    summary = tool + ': ' + JSON.stringify(args).substring(0, 100);
  }

  // Extract URL hash from output if available
  var urlHash = '';
  var outputStr = (toolOutput || '').substring(0, 2000);
  var hashMatch = outputStr.match(/#\/app\/[a-z0-9-]+/i);
  if (hashMatch) urlHash = hashMatch[0];

  var entry = {
    timestamp: new Date().toISOString(),
    tool: tool,
    action_summary: summary,
    url_hash: urlHash,
    server: server
  };

  try {
    var logDir = path.dirname(BLUEPRINT_ACTION_LOG);
    if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
    fs.appendFileSync(BLUEPRINT_ACTION_LOG, JSON.stringify(entry) + '\n');
  } catch (e) {}
  log('blueprint-logger', 'DEBUG', summary.substring(0, 80));
}

// ===== MAIN =====

async function main() {
  var input = '';
  for await (var chunk of process.stdin) input += chunk;

  var hookData;
  try { hookData = JSON.parse(input); } catch (e) { process.exit(0); }

  var toolName = hookData.tool_name || '';
  var toolInput = hookData.tool_input || {};
  var toolOutput = hookData.tool_output || '';

  // Module 3: Blueprint action logger (runs for mcpm calls)
  moduleBlueprintLogger(toolName, toolInput, toolOutput);

  // Identify what was invoked (for Skill/Task modules)
  var invokedId = null;
  if (toolName === 'Skill') {
    invokedId = toolInput.skill || null;
  } else if (toolName === 'Task') {
    invokedId = toolInput.name || toolInput.subagent_type || null;
  }

  if (!invokedId) {
    // mcpm calls don't have an invokedId -- that's fine, blueprint logger handled it
    if (toolName !== 'mcp__mcp-manager__mcpm') {
      log('main', 'DEBUG', 'no identifiable skill/mcp in tool_input');
    }
    process.exit(0);
  }

  // Get prompt snippet from state for logging
  var promptSnippet = '';
  try {
    if (fs.existsSync(STATE_FILE)) {
      var state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
      promptSnippet = state.prompt_snippet || '';
    }
  } catch (e) {}

  // Module 1: fulfillment tracker
  moduleFulfillmentTracker(invokedId);

  // Module 2: usage logger
  moduleUsageLogger(toolName, invokedId, promptSnippet);

  process.exit(0);
}

main().catch(function() { process.exit(0); });
