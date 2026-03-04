#!/usr/bin/env node
/**
 * @hook preference-learner
 * @event UserPromptSubmit
 * @matcher *
 * @description Learns user preferences from responses after interrupts.
 *   If previous interaction was an autonomous decision, captures user's
 *   actual choice and adds to learned preferences.
 */
const fs = require('fs');
const path = require('path');

const HOME = process.env.HOME || process.env.USERPROFILE;
const hooksDir = path.join(HOME, '.claude', 'hooks');
const logFile = path.join(hooksDir, 'hooks.log');
const prefsFile = path.join(hooksDir, 'user_preferences.json');
const lastDecisionFile = path.join(hooksDir, 'last_autonomous_decision.json');

function log(level, msg) {
  const ts = new Date().toISOString();
  const line = `${ts} [${level}] [UserPromptSubmit] [preference-learner] ${msg}\n`;
  try { fs.appendFileSync(logFile, line); } catch (e) {}
}

function loadPrefs() {
  try {
    return JSON.parse(fs.readFileSync(prefsFile, 'utf8'));
  } catch (e) {
    return { rules: [], learned: [], history: [] };
  }
}

function savePrefs(prefs) {
  try {
    fs.writeFileSync(prefsFile, JSON.stringify(prefs, null, 2));
  } catch (e) {}
}

// Read input
let input = '';
try { input = fs.readFileSync(0, 'utf-8'); } catch (e) { process.exit(0); }

let data;
try { data = JSON.parse(input); } catch (e) { process.exit(0); }

const prompt = (data.prompt || '').trim();

// Check if this looks like a correction to an autonomous decision
// Patterns: "no", "wrong", "actually", "I wanted", numbers (choosing different option)
const correctionPatterns = /^(no|nope|wrong|actually|not that|i (wanted|meant|said)|different|\d+)$/i;

if (!correctionPatterns.test(prompt)) {
  process.exit(0);
}

// Check if there was a recent autonomous decision
let lastDecision;
try {
  lastDecision = JSON.parse(fs.readFileSync(lastDecisionFile, 'utf8'));
  // Only consider if within last 2 minutes
  if (Date.now() - lastDecision.timestamp > 120000) {
    process.exit(0);
  }
} catch (e) {
  process.exit(0);
}

log('INFO', `detected correction: "${prompt}" for question: "${lastDecision.question}"`);

// Learn from this
const prefs = loadPrefs();
prefs.learned.push({
  timestamp: new Date().toISOString(),
  question: lastDecision.question,
  autonomousChoice: lastDecision.decision,
  userCorrection: prompt,
  context: 'user corrected autonomous decision'
});

// Keep last 50 learned items
if (prefs.learned.length > 50) prefs.learned = prefs.learned.slice(-50);

savePrefs(prefs);
log('INFO', 'saved learned preference from correction');

// Clean up
try { fs.unlinkSync(lastDecisionFile); } catch (e) {}

process.exit(0);
