#!/usr/bin/env node
/**
 * @hook skill-usage-tracker
 * @event PostToolUse
 * @matcher Skill|Task
 * @description Logs every Skill/Task invocation to skill-usage.jsonl for analytics
 */
const fs = require('fs');
const path = require('path');

const HOME = process.env.HOME || process.env.USERPROFILE;
const LOG_FILE = path.join(HOME, '.claude', 'hooks', 'hooks.log');
const STATE_FILE = path.join(HOME, '.claude', 'super-manager', 'state', 'super-manager-pending-suggestions.json');
const ENFORCE_LOG = path.join(HOME, '.claude', 'super-manager', 'logs', 'super-manager-enforcement.log');
const SKILL_USAGE_LOG = path.join(HOME, '.claude', 'super-manager', 'logs', 'skill-usage.jsonl');

function log(level, msg) {
  const ts = new Date().toISOString();
  fs.appendFileSync(LOG_FILE, `${ts} [${level}] [PostToolUse] [super-manager-check-enforcement] ${msg}\n`);
}

async function main() {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;

  let hookData;
  try { hookData = JSON.parse(input); } catch { process.exit(0); }

  const toolName = hookData.tool_name || '';
  const toolInput = hookData.tool_input || {};

  // Identify what was invoked
  let invokedId = null;
  if (toolName === 'Skill') {
    invokedId = toolInput.skill || null;
  } else if (toolName === 'Task') {
    // MCP tools come through Task tool
    invokedId = toolInput.name || toolInput.subagent_type || null;
  }

  if (!invokedId) {
    log('DEBUG', 'no identifiable skill/mcp in tool_input');
    process.exit(0);
  }

  // Read pending suggestions
  let state;
  try {
    if (!fs.existsSync(STATE_FILE)) { process.exit(0); }
    state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
  } catch { process.exit(0); }

  // Mark as fulfilled
  const fulfilled = new Set(state.fulfilled || []);
  let matched = false;

  // Check skills
  for (const s of (state.suggestions?.skills || [])) {
    if (s.id === invokedId || invokedId.includes(s.id)) {
      fulfilled.add(s.id);
      matched = true;
    }
  }

  // Check MCPs
  for (const m of (state.suggestions?.mcps || [])) {
    if (m.name === invokedId || invokedId.includes(m.name)) {
      fulfilled.add(m.name);
      matched = true;
    }
  }

  // Always log skill/task usage to JSONL for analytics
  const ts = new Date().toISOString();
  const usageEntry = {
    timestamp: ts,
    tool: toolName,
    skill: invokedId,
    prompt_snippet: (state.prompt_snippet || '').slice(0, 100),
    had_suggestion: matched
  };
  try {
    const logDir = path.dirname(SKILL_USAGE_LOG);
    if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
    fs.appendFileSync(SKILL_USAGE_LOG, JSON.stringify(usageEntry) + '\n');
  } catch {}

  if (matched) {
    state.fulfilled = Array.from(fulfilled);
    try {
      fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
    } catch {}
    log('INFO', 'fulfilled: ' + invokedId);
  } else {
    log('DEBUG', 'invoked ' + invokedId + ' (no matching suggestion)');
  }
}

main().catch(() => process.exit(0));
