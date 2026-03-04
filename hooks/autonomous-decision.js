#!/usr/bin/env node
/**
 * @hook autonomous-decision
 * @event PreToolUse
 * @matcher AskUserQuestion
 * @description Auto-answers questions when autonomous mode is enabled.
 *   Reads GSD context, user preferences, and uses claude -p to decide.
 *   Only exits autonomous mode when GSD verifier says complete.
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const HOME = process.env.HOME || process.env.USERPROFILE;
const hooksDir = path.join(HOME, '.claude', 'hooks');
const logFile = path.join(hooksDir, 'hooks.log');
const stateFile = path.join(hooksDir, 'autonomous_mode.state');
const prefsFile = path.join(hooksDir, 'user_preferences.json');
const lastDecisionFile = path.join(hooksDir, 'last_autonomous_decision.json');
const tempDir = process.env.TEMP || '/tmp';

function log(level, msg) {
  const ts = new Date().toISOString();
  const line = `${ts} [${level}] [PreToolUse] [autonomous-decision] ${msg}\n`;
  try { fs.appendFileSync(logFile, line); } catch (e) {}
}

function isAutonomousEnabled() {
  try {
    return fs.readFileSync(stateFile, 'utf8').trim() === '1';
  } catch (e) {
    return true; // Default enabled
  }
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
  } catch (e) {
    log('ERROR', `Failed to save prefs: ${e.message}`);
  }
}

function saveLastDecision(question, decision) {
  try {
    fs.writeFileSync(lastDecisionFile, JSON.stringify({
      timestamp: Date.now(),
      question: question,
      decision: decision
    }));
  } catch (e) {
    log('ERROR', `Failed to save last decision: ${e.message}`);
  }
}

function readGSDContext(cwd) {
  const context = {};
  const planningDir = path.join(cwd, '.planning');
  
  // Read STATE.md
  try {
    context.state = fs.readFileSync(path.join(planningDir, 'STATE.md'), 'utf8').slice(0, 2000);
  } catch (e) {}
  
  // Read ROADMAP.md
  try {
    context.roadmap = fs.readFileSync(path.join(planningDir, 'ROADMAP.md'), 'utf8').slice(0, 2000);
  } catch (e) {}
  
  // Find latest PLAN.md
  const quickDir = path.join(planningDir, 'quick');
  if (fs.existsSync(quickDir)) {
    const tasks = fs.readdirSync(quickDir).filter(d => /^\d{3}-/.test(d)).sort().reverse();
    if (tasks.length > 0) {
      const latestTask = tasks[0];
      const num = latestTask.match(/^(\d{3})/)[1];
      try {
        context.plan = fs.readFileSync(path.join(quickDir, latestTask, `${num}-PLAN.md`), 'utf8');
      } catch (e) {}
    }
  }
  
  return context;
}

function makeDecision(question, options, gsdContext, prefs) {
  // Build prompt for claude -p
  const prompt = `You are an autonomous decision agent. Make a decision for this question based on context.

QUESTION:
${question}

OPTIONS:
${options.map((o, i) => `${i + 1}. ${o.label}: ${o.description || ''}`).join('\n')}

GSD CONTEXT:
State: ${gsdContext.state || 'none'}
Current Plan: ${gsdContext.plan || 'none'}

USER PREFERENCES:
${prefs.rules.map(r => `- ${r.pattern}: ${r.preference}`).join('\n')}

LEARNED FROM HISTORY:
${prefs.learned.slice(-5).map(l => `- Q: "${l.question}" -> Chose: ${l.choice || l.autonomousChoice}`).join('\n') || 'none yet'}

INSTRUCTIONS:
1. Analyze the question in context of the current task
2. Consider user's known preferences
3. Choose the option that best advances the goal
4. Respond with ONLY a number (1, 2, 3, etc.)

YOUR DECISION (number only):`;

  // Write to temp file
  const tempFile = path.join(tempDir, `autonomous_decision_${Date.now()}.txt`);
  fs.writeFileSync(tempFile, prompt);
  
  try {
    // Call claude -p with timeout
    const result = execSync(`claude -p "$(cat '${tempFile}')" --max-turns 1 2>/dev/null`, {
      timeout: 30000,
      encoding: 'utf8',
      shell: true
    }).trim();
    
    fs.unlinkSync(tempFile);
    
    // Extract decision (first number or line)
    const match = result.match(/(\d+)/);
    if (match) {
      return { type: 'option', value: parseInt(match[1]) };
    }
    return { type: 'custom', value: result.slice(0, 200) };
  } catch (e) {
    log('ERROR', `claude -p failed: ${e.message}`);
    try { fs.unlinkSync(tempFile); } catch (e) {}
    return { type: 'option', value: 1 }; // Default to first option
  }
}

// Main
let input = '';
try { input = fs.readFileSync(0, 'utf-8'); } catch (e) { process.exit(0); }

let data;
try { data = JSON.parse(input); } catch (e) { process.exit(0); }

const toolName = data.tool_name || '';
const toolInput = data.tool_input || {};
const cwd = data.cwd || process.cwd();

// Only handle AskUserQuestion
if (toolName !== 'AskUserQuestion') {
  process.exit(0);
}

// Check autonomous mode
if (!isAutonomousEnabled()) {
  log('DEBUG', 'autonomous mode disabled - allowing question');
  process.exit(0);
}

// Extract question data
const questions = toolInput.questions || [];
if (questions.length === 0) {
  log('DEBUG', 'no questions in input');
  process.exit(0);
}

const q = questions[0];
const questionText = q.question || '';
const options = q.options || [];

log('INFO', `intercepting question: ${questionText.slice(0, 50)}...`);

// Load context
const gsdContext = readGSDContext(cwd);
const prefs = loadPrefs();

// Make decision
const decision = makeDecision(questionText, options, gsdContext, prefs);
log('INFO', `decided: ${JSON.stringify(decision)}`);

// Determine answer
let answer;
if (decision.type === 'option' && decision.value <= options.length) {
  answer = options[decision.value - 1].label;
} else if (decision.type === 'custom') {
  answer = decision.value;
} else {
  answer = options[0]?.label || 'proceed';
}

// Save for preference learning
saveLastDecision(questionText, answer);

// Save to history
prefs.history.push({
  timestamp: new Date().toISOString(),
  question: questionText.slice(0, 100),
  options: options.map(o => o.label),
  decision: decision,
  answer: answer
});
if (prefs.history.length > 100) prefs.history = prefs.history.slice(-100);
savePrefs(prefs);

// Output the decision and block the question
console.log(`<autonomous-decision>
AUTONOMOUS MODE: Auto-answering question.
Question: ${questionText}
Decision: ${answer}
Reasoning: Based on GSD context and user preferences.
Continue with this choice.
</autonomous-decision>`);

// Block the AskUserQuestion tool - Claude will see the decision and proceed
process.exit(2);
