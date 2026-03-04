#!/usr/bin/env node
/**
 * @hook auto-gsd
 * @event UserPromptSubmit
 * @matcher *
 * @description Creates .planning/ structure for ALL user requests.
 *   SLOW AND ACCURATE > FAST AND WRONG
 *   NO EXCEPTIONS - every task gets tracked.
 */
const fs = require('fs');
const path = require('path');

const logFile = path.join(process.env.HOME || process.env.USERPROFILE, '.claude', 'hooks', 'hooks.log');
function log(level, msg) {
  const ts = new Date().toISOString();
  const line = `${ts} [${level}] [UserPromptSubmit] [auto-gsd] ${msg}\n`;
  try { fs.appendFileSync(logFile, line); } catch (e) {}
}

let input = '';
try { input = fs.readFileSync(0, 'utf-8'); } catch (e) { process.exit(0); }

let data;
try { data = JSON.parse(input); } catch (e) { process.exit(0); }

const prompt = (data.prompt || '').trim();
const cwd = data.cwd || process.cwd();

// ONLY skip /gsd commands (they handle their own tracking)
if (prompt.startsWith('/gsd')) {
  log('DEBUG', 'skipped - GSD command handles own tracking');
  process.exit(0);
}

// Skip empty prompts
if (!prompt) {
  process.exit(0);
}

// Check for GSD project
const planningDir = path.join(cwd, '.planning');
const roadmapPath = path.join(planningDir, 'ROADMAP.md');
const hasGSD = fs.existsSync(roadmapPath);

if (!hasGSD) {
  log('INFO', 'no .planning/ - creating structure');
  
  const quickDir = path.join(planningDir, 'quick');
  
  try {
    fs.mkdirSync(quickDir, { recursive: true });
    
    fs.writeFileSync(path.join(planningDir, 'ROADMAP.md'), `# Roadmap

## Active Milestone: Quick Tasks

This project uses GSD quick tasks for ad-hoc work.

---
*Auto-initialized by auto-gsd hook*
`);

    fs.writeFileSync(path.join(planningDir, 'STATE.md'), `# Project State

## Current Position
Phase: Quick tasks mode
Status: Ready
Last activity: ${new Date().toISOString().split('T')[0]} — Auto-initialized

## Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
`);

    fs.writeFileSync(path.join(planningDir, 'config.json'), JSON.stringify({
      mode: "yolo",
      depth: "quick",
      parallelization: true,
      commit_docs: true,
      workflow: {
        research: false,
        plan_check: false,
        verifier: true
      },
      auto_initialized: true
    }, null, 2));

    log('INFO', 'created .planning/ structure');
    console.log('<auto-gsd mode="initialized">GSD structure created. You MUST create PLAN.md before executing.</auto-gsd>');
  } catch (e) {
    log('ERROR', `failed to create .planning/: ${e.message}`);
    process.exit(0);
  }
} else {
  log('DEBUG', 'GSD project exists');
  // Remind Claude about the requirement
  console.log('<auto-gsd mode="reminder">GSD tracking active. PLAN.md required before Write/Edit only. Bash, Task, WebFetch, agents always allowed.</auto-gsd>');
}

process.exit(0);
