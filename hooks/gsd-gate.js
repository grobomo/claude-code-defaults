#!/usr/bin/env node
/**
 * @hook gsd-gate
 * @event PreToolUse
 * @matcher Bash|Write|Edit|Task|WebFetch
 * @description Blocks execution tools until PLAN.md exists.
 *   SLOW AND ACCURATE > FAST AND WRONG
 *   Claude must define success criteria BEFORE any implementation.
 */
const fs = require('fs');
const path = require('path');

const logFile = path.join(process.env.HOME || process.env.USERPROFILE, '.claude', 'hooks', 'hooks.log');
function log(level, msg) {
  const ts = new Date().toISOString();
  const line = `${ts} [${level}] [PreToolUse] [gsd-gate] ${msg}\n`;
  try { fs.appendFileSync(logFile, line); } catch (e) {}
}

let input = '';
try { input = fs.readFileSync(0, 'utf-8'); } catch (e) { process.exit(0); }

let data;
try { data = JSON.parse(input); } catch (e) { process.exit(0); }

const toolName = data.tool_name || '';
const cwd = data.cwd || process.cwd();

// Gate execution tools - read-only tools allowed without plan
const GATED_TOOLS = ['Write', 'Edit'];
if (!GATED_TOOLS.includes(toolName)) {
  process.exit(0); // Read, Glob, Grep allowed for research
}

// Check for GSD project
const configPath = path.join(cwd, '.planning', 'config.json');
if (!fs.existsSync(configPath)) {
  log('DEBUG', 'no .planning/config.json - not a GSD project');
  process.exit(0);
}

let config;
try {
  config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
} catch (e) {
  log('ERROR', `failed to read config: ${e.message}`);
  process.exit(0);
}

// Only enforce for auto-initialized projects
if (!config.auto_initialized) {
  process.exit(0);
}

// Check for PLAN.md in quick task directory
const quickDir = path.join(cwd, '.planning', 'quick');
if (!fs.existsSync(quickDir)) {
  fs.mkdirSync(quickDir, { recursive: true });
}

// Find task directories
const taskDirs = fs.readdirSync(quickDir)
  .filter(d => /^\d{3}-/.test(d))
  .sort()
  .reverse();

if (taskDirs.length === 0) {
  log('INFO', 'no task dirs - blocking until PLAN.md created');
  console.log('<gsd-gate action="blocked">\n' +
    'STOP: Create a plan before executing.\n\n' +
    'Required steps:\n' +
    '1. mkdir -p .planning/quick/001-task-slug/\n' +
    '2. Write 001-PLAN.md with Goal + Success Criteria\n' +
    '3. Then execute\n\n' +
    'SLOW AND ACCURATE > FAST AND WRONG\n' +
    '</gsd-gate>');
  process.exit(2);
}

// Check latest task for PLAN.md
const latestTask = taskDirs[0];
const taskNum = latestTask.match(/^(\d{3})/)[1];
const planPath = path.join(quickDir, latestTask, `${taskNum}-PLAN.md`);

if (!fs.existsSync(planPath)) {
  log('INFO', `no PLAN.md in ${latestTask} - blocking`);
  console.log('<gsd-gate action="blocked">\n' +
    `STOP: No PLAN.md in .planning/quick/${latestTask}/\n\n` +
    `Write ${taskNum}-PLAN.md with:\n` +
    '## Goal\n[What needs to happen]\n\n' +
    '## Success Criteria\n- [ ] Criterion 1\n- [ ] Criterion 2\n\n' +
    '## Tasks\n1. Step one\n2. Step two\n\n' +
    'SLOW AND ACCURATE > FAST AND WRONG\n' +
    '</gsd-gate>');
  process.exit(2);
}

log('DEBUG', `PLAN.md exists - allowing ${toolName}`);
process.exit(0);
