#!/usr/bin/env node
/**
 * @hook gsd-verifier-check
 * @event PostToolUse
 * @matcher Task
 * @description Monitors for GSD verifier completion to exit autonomous mode.
 *   Only disables autonomous mode when verifier confirms task complete.
 */
const fs = require('fs');
const path = require('path');

const HOME = process.env.HOME || process.env.USERPROFILE;
const hooksDir = path.join(HOME, '.claude', 'hooks');
const logFile = path.join(hooksDir, 'hooks.log');
const stateFile = path.join(hooksDir, 'autonomous_mode.state');

function log(level, msg) {
  const ts = new Date().toISOString();
  const line = `${ts} [${level}] [PostToolUse] [gsd-verifier-check] ${msg}\n`;
  try { fs.appendFileSync(logFile, line); } catch (e) {}
}

// Read input
let input = '';
try { input = fs.readFileSync(0, 'utf-8'); } catch (e) { process.exit(0); }

let data;
try { data = JSON.parse(input); } catch (e) { process.exit(0); }

const toolName = data.tool_name || '';
const toolInput = data.tool_input || {};
const toolResult = data.tool_result || '';

// Only check Task tool calls
if (toolName !== 'Task') {
  process.exit(0);
}

// Check if this was a verifier agent
const subagentType = toolInput.subagent_type || '';
const prompt = toolInput.prompt || '';
const description = toolInput.description || '';

const isVerifier = 
  subagentType.includes('verifier') ||
  prompt.toLowerCase().includes('verify') ||
  description.toLowerCase().includes('verify');

if (!isVerifier) {
  process.exit(0);
}

// Check if result indicates completion
const resultLower = toolResult.toLowerCase();
const completionIndicators = [
  'verification complete',
  'all criteria met',
  'task complete',
  'successfully verified',
  'phase complete',
  'gsd complete'
];

const isComplete = completionIndicators.some(ind => resultLower.includes(ind));

if (isComplete) {
  log('INFO', 'GSD verifier confirmed completion - disabling autonomous mode');
  try {
    fs.writeFileSync(stateFile, '0');
    console.log('<gsd-verifier-check>\nGSD COMPLETE: Autonomous mode disabled. Awaiting next task.\n</gsd-verifier-check>');
  } catch (e) {
    log('ERROR', `Failed to update state: ${e.message}`);
  }
} else {
  log('DEBUG', 'verifier ran but task not complete - autonomous mode continues');
}

process.exit(0);
