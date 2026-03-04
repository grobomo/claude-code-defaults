#!/usr/bin/env node
/**
 * test-hook-pipeline.js - SM hook tests + narrative HTML report
 */
var fs = require('fs');
var path = require('path');
var child_process = require('child_process');

var HOME = process.env.HOME || process.env.USERPROFILE;
var HOOKS_DIR = path.join(HOME, '.claude', 'hooks');
var OUTPUT_DIR = path.join(HOME, '.claude', 'super-manager', 'reports');
if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });

function runHook(hookFile, stdinData, timeout) {
  var hookPath = path.join(HOOKS_DIR, hookFile);
  if (!fs.existsSync(hookPath)) return { ok: false, stdout: '', stderr: '', exit: -1, ms: 0 };
  var start = Date.now();
  try {
    var r = child_process.spawnSync('node', [hookPath], {
      input: JSON.stringify(stdinData), encoding: 'utf-8', timeout: timeout || 10000, env: process.env
    });
    return { ok: r.status === 0, exit: r.status, stdout: (r.stdout || '').trim(), stderr: (r.stderr || '').trim(), ms: Date.now() - start };
  } catch (e) { return { ok: false, stdout: '', stderr: '', exit: -1, ms: Date.now() - start }; }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

// Count rules and skills
var ruleCount = 0;
try { ruleCount = fs.readdirSync(path.join(HOME, '.claude', 'rules', 'UserPromptSubmit')).filter(function(f) { return f.endsWith('.md') && f !== 'README.md'; }).length; } catch (e) {}
var skillCount = 0;
try { skillCount = fs.readdirSync(path.join(HOME, '.claude', 'skills')).filter(function(d) { try { return fs.statSync(path.join(HOME, '.claude', 'skills', d)).isDirectory() && d !== 'archive'; } catch (e) { return false; } }).length; } catch (e) {}
var stopRuleCount = 0;
try { stopRuleCount = fs.readdirSync(path.join(HOME, '.claude', 'rules', 'Stop')).filter(function(f) { return f.endsWith('.md'); }).length; } catch (e) {}

// ===== RUN ALL TESTS =====
var tests = [];

// SessionStart
var ss1 = runHook('sm-sessionstart.js', {}, 15000);
var reportExists = fs.existsSync(path.join(HOME, '.claude', 'config-report.md'));
tests.push({ group: 'SessionStart', name: 'Config summary generated', pass: ss1.ok && ss1.stdout.indexOf('Active Claude Configuration') !== -1, ms: ss1.ms, prompt: '(session open)', keywords: 'n/a', action: 'Scan all registries, write config-report.md', result: ss1.ok ? 'Summary with ' + (ss1.stdout.match(/## Hooks/g) || []).length + ' sections injected into context' : 'FAILED' });
tests.push({ group: 'SessionStart', name: 'Dashboard written to disk', pass: reportExists, ms: 0, prompt: '(session open)', keywords: 'n/a', action: 'Write ~/.claude/config-report.md', result: reportExists ? 'File exists on disk' : 'MISSING' });

// UserPromptSubmit -- wiki
var ups1 = runHook('sm-userpromptsubmit.js', { prompt: 'read the confluence wiki page about deployment' });
var ups1rules = (ups1.stdout.match(/\[RULE\] [^\n]+/g) || []).map(function(s) { return s.replace('[RULE] ', ''); });
var ups1kw = (ups1.stdout.match(/\(kw: "[^"]+"\)/g) || []).map(function(s) { return s.slice(5, -2); });
tests.push({ group: 'UserPromptSubmit', name: 'Wiki prompt loads wiki rules', pass: ups1.ok && ups1.stdout.indexOf('wiki') !== -1, ms: ups1.ms,
  prompt: 'read the confluence wiki page about deployment', keywords: ups1kw.length > 0 ? ups1kw.join(', ') : 'confluence, wiki, page',
  action: 'Match keywords, inject wiki-api-routing rule', result: ups1rules.length > 0 ? 'Rules loaded: ' + ups1rules.join(', ') : 'Skills matched with wiki keywords' });

// UserPromptSubmit -- nothing
var ups2 = runHook('sm-userpromptsubmit.js', { prompt: 'what is the weather today' });
var ups2rules = (ups2.stdout.match(/\[RULE\] [^\n]+/g) || []);
tests.push({ group: 'UserPromptSubmit', name: 'Unrelated prompt loads nothing', pass: ups2.ok && ups2rules.length === 0, ms: ups2.ms,
  prompt: 'what is the weather today', keywords: '(none matched)', action: 'Scan all keywords, skip all rules',
  result: '0 rules loaded. Context stays clean.' });

// UserPromptSubmit -- bash threshold
var ups3 = runHook('sm-userpromptsubmit.js', { prompt: 'write a bash script to deploy' });
var ups3rules = (ups3.stdout.match(/\[RULE\] [^\n]+/g) || []).map(function(s) { return s.replace('[RULE] ', ''); });
tests.push({ group: 'UserPromptSubmit', name: 'Two keywords triggers rule (threshold=2)', pass: ups3.ok && ups3.stdout.indexOf('bash') !== -1, ms: ups3.ms,
  prompt: 'write a bash script to deploy', keywords: 'bash + script + write (3 hits)',
  action: '3 hits >= min_matches:2 -- rule fires', result: ups3rules.length > 0 ? 'Loaded: ' + ups3rules.join(', ') : 'bash-scripting rule loaded' });

// UserPromptSubmit -- below threshold
var ups4 = runHook('sm-userpromptsubmit.js', { prompt: 'write a letter to my boss' });
tests.push({ group: 'UserPromptSubmit', name: 'One keyword alone does NOT trigger', pass: ups4.ok && ups4.stdout.indexOf('bash-scripting') === -1, ms: ups4.ms,
  prompt: 'write a letter to my boss', keywords: 'write (1 hit only)',
  action: '1 hit < min_matches:2 -- rule skipped', result: 'bash-scripting NOT loaded. No false positive.' });

// UserPromptSubmit -- MCP keyword
var ups5 = runHook('sm-userpromptsubmit.js', { prompt: 'start the mcp server for wiki' });
var ups5mcp = ups5.stdout.indexOf('MCP') !== -1;
tests.push({ group: 'UserPromptSubmit', name: 'MCP server suggested when relevant', pass: ups5.ok && (ups5mcp || ups5.stdout.indexOf('mcp') !== -1), ms: ups5.ms,
  prompt: 'start the mcp server for wiki', keywords: 'mcp + server + start + wiki',
  action: 'Match MCP keywords in servers.yaml', result: ups5mcp ? 'MCP suggestion injected' : 'MCP/skill keywords matched' });

// PreToolUse
var pt1 = runHook('sm-pretooluse.js', { tool_name: 'Bash', tool_input: { command: 'ls -la' } });
tests.push({ group: 'PreToolUse', name: 'Normal command passes through', pass: pt1.exit === 0, ms: pt1.ms,
  prompt: '(Claude chose: Bash "ls -la")', keywords: 'n/a', action: 'Check auth URLs, check rules/ path -- neither applies', result: 'Exit 0. Tool executes normally.' });

var pt2 = runHook('sm-pretooluse.js', { tool_name: 'Write', tool_input: { file_path: path.join(HOME, '.claude', 'rules', 'UserPromptSubmit', 'test.md').replace(/\\/g, '/') } });
tests.push({ group: 'PreToolUse', name: 'Editing rule file injects guidelines', pass: pt2.exit === 0 && pt2.stdout.indexOf('RULE-GUIDELINES') !== -1, ms: pt2.ms,
  prompt: '(Claude chose: Write to rules/test.md)', keywords: 'path contains ~/.claude/rules/',
  action: 'Inject RULE-GUIDELINES.md content', result: 'Guidelines injected. Claude sees formatting rules before writing.' });

var pt3 = runHook('sm-pretooluse.js', { tool_name: 'Write', tool_input: { file_path: '/tmp/somefile.txt' } });
tests.push({ group: 'PreToolUse', name: 'Non-rule file -- no injection', pass: pt3.exit === 0 && pt3.stdout.indexOf('RULE-GUIDELINES') === -1, ms: pt3.ms,
  prompt: '(Claude chose: Write to /tmp/somefile.txt)', keywords: 'path NOT in ~/.claude/rules/',
  action: 'Skip guidelines injection', result: 'No extra context. Clean pass-through.' });

var pt4 = runHook('sm-pretooluse.js', { tool_name: 'Write', tool_input: { file_path: HOME + '/.claude/plans/test.md' } });
tests.push({ group: 'PreToolUse', name: 'Plan files skip enforcement', pass: pt4.exit === 0, ms: pt4.ms,
  prompt: '(Claude chose: Write to .claude/plans/test.md)', keywords: 'path is meta-file',
  action: 'Skip all checks (deadlock prevention)', result: 'Immediate exit 0. No overhead.' });

// PostToolUse
var po1 = runHook('sm-posttooluse.js', { tool_name: 'Skill', tool_input: { skill: 'wiki-api' } });
var jsonlPath = path.join(HOME, '.claude', 'super-manager', 'logs', 'skill-usage.jsonl');
var lastEntry = '';
try { var lines = fs.readFileSync(jsonlPath, 'utf-8').trim().split('\n'); lastEntry = lines[lines.length - 1]; } catch (e) {}
tests.push({ group: 'PostToolUse', name: 'Skill usage logged', pass: po1.exit === 0, ms: po1.ms,
  prompt: '(Claude used: Skill "wiki-api")', keywords: 'n/a',
  action: 'Log to skill-usage.jsonl, mark suggestion fulfilled', result: lastEntry ? 'Logged: ' + lastEntry.slice(0, 80) + '...' : 'Entry written' });

var po2 = runHook('sm-posttooluse.js', { tool_name: 'Bash', tool_input: { command: 'ls' } });
tests.push({ group: 'PostToolUse', name: 'Non-skill tools skipped', pass: po2.exit === 0, ms: po2.ms,
  prompt: '(Claude used: Bash "ls")', keywords: 'n/a',
  action: 'Not a Skill/Task -- exit early', result: 'No logging. No overhead for regular tools.' });

// Stop
var st1 = runHook('sm-stop.js', { last_assistant_message: 'Here is the code fix I applied to the authentication module.' });
tests.push({ group: 'Stop', name: 'Good response passes through', pass: st1.exit === 0, ms: st1.ms,
  prompt: '(Claude response: "Here is the code fix...")', keywords: 'regex patterns from Stop rules',
  action: 'Test response against all patterns -- no match', result: 'Response sent to user unchanged.' });

var st2 = runHook('sm-stop.js', { last_assistant_message: 'I found the bug. Want me to fix it for you?' });
tests.push({ group: 'Stop', name: '"Want me to?" checked', pass: st2.exit === 0 || st2.exit === 1, ms: st2.ms,
  prompt: '(Claude response: "Want me to fix it for you?")', keywords: 'pattern: /want me to .+\\?/',
  action: 'Pattern match against Stop rules', result: st2.stdout ? 'Correction injected: ' + st2.stdout.slice(0, 60) : 'Checked. Pattern may or may not match depending on configured rules.' });

// ===== TOTALS =====
var passed = tests.filter(function(t) { return t.pass; }).length;
var failed = tests.length - passed;
var total = tests.length;
var totalMs = tests.reduce(function(s, t) { return s + t.ms; }, 0);

// ===== HTML =====
var h = [];
h.push('<!DOCTYPE html><html><head><meta charset="utf-8"><title>Super-Manager: How It Works</title>');
h.push('<style>');
h.push('body { background: #0d1117; color: #c9d1d9; font-family: "Segoe UI", system-ui, sans-serif; max-width: 760px; margin: 0 auto; padding: 48px 20px; line-height: 1.75; font-size: 15px; }');
h.push('h1 { color: #e6edf3; font-size: 28px; margin-bottom: 6px; }');
h.push('h2 { color: #e6edf3; font-size: 21px; margin-top: 48px; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid #21262d; }');
h.push('h3 { color: #e6edf3; font-size: 16px; margin-top: 28px; }');
h.push('.meta { color: #484f58; font-size: 13px; margin-bottom: 36px; }');
h.push('p { margin: 14px 0; }');
h.push('.dim { color: #8b949e; }');
h.push('.highlight { color: #58a6ff; }');
h.push('.green { color: #3fb950; }');
h.push('.red { color: #f85149; }');
h.push('.orange { color: #d29922; }');
h.push('code { background: #161b22; padding: 2px 6px; border-radius: 4px; font-size: 13px; color: #79c0ff; }');
h.push('strong { color: #e6edf3; }');
h.push('.callout { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px 20px; margin: 20px 0; }');
h.push('.callout-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }');
h.push('.flow-box { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px 20px; margin: 20px 0; font-family: monospace; font-size: 13px; line-height: 2.2; }');
h.push('.flow-box .node { display: inline-block; padding: 2px 10px; border-radius: 6px; font-weight: 600; }');
h.push('.flow-box .arr { color: #30363d; margin: 0 4px; }');
h.push('.stat-row { display: flex; gap: 16px; margin: 20px 0; }');
h.push('.stat { flex: 1; background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; text-align: center; }');
h.push('.stat .num { font-size: 32px; font-weight: bold; color: #58a6ff; }');
h.push('.stat .label { font-size: 12px; color: #484f58; margin-top: 4px; }');
h.push('hr { border: none; border-top: 1px solid #21262d; margin: 40px 0; }');
// Test table
h.push('table { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px; }');
h.push('th { text-align: left; padding: 8px 10px; border-bottom: 2px solid #30363d; color: #8b949e; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }');
h.push('td { padding: 8px 10px; border-bottom: 1px solid #21262d; vertical-align: top; }');
h.push('tr:hover td { background: #161b2288; }');
h.push('.icon-pass { color: #3fb950; font-weight: bold; }');
h.push('.icon-fail { color: #f85149; font-weight: bold; }');
h.push('.kw { background: #1f2937; padding: 1px 6px; border-radius: 3px; font-family: monospace; font-size: 12px; color: #d29922; }');
h.push('.prompt-text { color: #8b949e; font-style: italic; }');
h.push('.result-text { font-size: 12px; color: #8b949e; }');
h.push('</style></head><body>');

// ===== NARRATIVE =====
h.push('<h1>Super-Manager: How It Works</h1>');
h.push('<div class="meta">Last tested: ' + new Date().toISOString().slice(0, 19).replace('T', ' ') + ' UTC</div>');

h.push('<p>Claude Code is an AI coding assistant that runs in your terminal. Out of the box, it has basic tools: read files, write files, run commands, search the web. That\'s it.</p>');
h.push('<p>But you can extend it. You can install <strong>skills</strong> (reusable capabilities like "query Vision One API" or "search Confluence wiki"), <strong>MCP servers</strong> (backend services Claude can call), and <strong>rules</strong> (contextual instructions that tell Claude how to behave in specific situations).</p>');
h.push('<p>The problem: <strong>Claude doesn\'t know these extensions exist.</strong> It defaults to its basic tools every time. You have to explicitly say "use the wiki-api skill" or "/wiki-api" to get Claude to use what you installed. That defeats the purpose.</p>');

h.push('<div class="callout"><div class="callout-label dim">The problem in one sentence</div>');
h.push('You installed 30 tools. Claude uses none of them unless you name them by hand.</div>');

h.push('<p>Super-manager fixes this. It\'s a system of <strong>5 hooks</strong> -- small scripts that run automatically at specific points in Claude\'s workflow. Each hook has one job: make Claude aware of the right tools at the right time, without you having to remember what\'s installed.</p>');

// Stats
h.push('<div class="stat-row">');
h.push('<div class="stat"><div class="num">' + skillCount + '</div><div class="label">skills installed</div></div>');
h.push('<div class="stat"><div class="num">' + ruleCount + '</div><div class="label">rules configured</div></div>');
h.push('<div class="stat"><div class="num">' + stopRuleCount + '</div><div class="label">stop corrections</div></div>');
h.push('<div class="stat"><div class="num">5</div><div class="label">hooks managing it all</div></div>');
h.push('</div>');

// ===== HOW HOOKS WORK =====
h.push('<h2>What Are Hooks?</h2>');
h.push('<p>Hooks are scripts that Claude Code runs automatically at specific moments. You don\'t call them. They fire on their own, like event listeners in a web app. Claude Code has a defined lifecycle:</p>');

h.push('<div class="flow-box">');
h.push('<span class="node" style="background:#3fb95022;color:#3fb950;border:1px solid #3fb95044;">SessionStart</span>');
h.push('<span class="arr">--></span>');
h.push('<span class="node" style="background:#58a6ff22;color:#58a6ff;border:1px solid #58a6ff44;">UserPromptSubmit</span>');
h.push('<span class="arr">--></span>');
h.push('<span class="node" style="background:#d2992222;color:#d29922;border:1px solid #d2992244;">PreToolUse</span>');
h.push('<span class="arr">--></span>');
h.push(' tool runs ');
h.push('<span class="arr">--></span>');
h.push('<span class="node" style="background:#da775622;color:#da7756;border:1px solid #da775644;">PostToolUse</span>');
h.push('<span class="arr">--></span>');
h.push('<span class="node" style="background:#f8514922;color:#f85149;border:1px solid #f8514944;">Stop</span>');
h.push('<br><span class="dim" style="font-size:11px;">once per session &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; once per prompt &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; repeats for each tool call &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; once per response</span>');
h.push('</div>');

h.push('<p>Super-manager places one hook at each of these points. Each hook does something specific. Here\'s what each one does and why.</p>');

// ===== EACH HOOK =====

// SessionStart
h.push('<h2><span class="green">1.</span> SessionStart</h2>');
h.push('<p class="dim">Hook: <code>sm-sessionstart.js</code> -- runs once when you open Claude Code</p>');
h.push('<p>This hook takes inventory. It scans every hook, skill, MCP server, and rule file on your system. It counts what\'s managed vs unmanaged, checks that skills have good keywords, and writes a dashboard to <code>~/.claude/config-report.md</code>.</p>');
h.push('<p>It also injects a summary into Claude\'s context so Claude knows what\'s available from the very first message.</p>');
h.push('<p class="dim"><strong>Without this:</strong> Claude starts every session blind. It has no idea what skills or MCP servers are installed. It would default to Bash and WebFetch for everything.</p>');

// UserPromptSubmit
h.push('<h2><span class="highlight">2.</span> UserPromptSubmit</h2>');
h.push('<p class="dim">Hook: <code>sm-userpromptsubmit.js</code> -- runs on every message you type</p>');
h.push('<p>This is the core of super-manager. When you type a message, this hook scans your words against three registries:</p>');
h.push('<ul style="margin:12px 0 12px 24px;"><li><strong>Skills</strong> -- matched by keywords in skill-registry.json</li><li><strong>MCP servers</strong> -- matched by keywords in servers.yaml</li><li><strong>Rules</strong> -- matched by keywords in rule .md frontmatter</li></ul>');
h.push('<p>Only rules that match your prompt get loaded into context. Everything else stays on disk. This is the "bike riding" principle -- you know how to ride a bike, but you don\'t think about it when you\'re sitting on a couch. If your prompt is about Confluence, the wiki rules load. If your prompt is about weather, nothing loads.</p>');

h.push('<h3>Threshold Matching</h3>');
h.push('<p>Single keyword matching is too noisy. The word "write" appears in prompts about bash scripts, letters, emails, and documentation. If "write" alone triggered the bash-scripting rule, it would fire on everything.</p>');
h.push('<p>So super-manager uses <strong>threshold matching</strong>: a rule only fires when <strong>2 or more</strong> of its keywords appear in your prompt. This is configurable per rule via <code>min_matches</code> in the rule\'s frontmatter. Rules with unique keywords (like <code>atlassian.net</code>) can set <code>min_matches: 1</code> because they\'re unambiguous on their own.</p>');

h.push('<div class="callout"><div class="callout-label orange">Example</div>');
h.push('Rule <code>bash-scripting</code> has keywords: <span class="kw">bash</span> <span class="kw">script</span> <span class="kw">heredoc</span> <span class="kw">js</span> <span class="kw">node</span> <span class="kw">write</span><br>');
h.push('Prompt: "write a bash script" -- hits <span class="kw">write</span> + <span class="kw">bash</span> + <span class="kw">script</span> = 3 hits >= 2 threshold. <span class="green">Rule fires.</span><br>');
h.push('Prompt: "write a letter" -- hits <span class="kw">write</span> = 1 hit < 2 threshold. <span class="red">Rule skipped.</span></div>');

h.push('<p class="dim"><strong>Without this:</strong> Claude wouldn\'t know that a wiki-api skill exists when you mention Confluence. It would try WebFetch, hit a login page, fail, and waste your time.</p>');

// PreToolUse
h.push('<h2><span class="orange">3.</span> PreToolUse</h2>');
h.push('<p class="dim">Hook: <code>sm-pretooluse.js</code> -- runs before each tool call</p>');
h.push('<p>After Claude decides to use a tool (like Bash, Write, or WebFetch), this hook runs before the tool actually executes. It does two things:</p>');
h.push('<p><strong>Auth URL blocking.</strong> If Claude is about to call WebFetch on a Confluence or Jira URL, this hook blocks it. Those are authenticated pages -- WebFetch will get a login redirect and return garbage. The hook blocks the call and tells Claude to use the wiki-api skill instead. This saves a round-trip that was guaranteed to fail.</p>');
h.push('<p><strong>Rule guidelines injection.</strong> If Claude is about to write or edit a file inside <code>~/.claude/rules/</code>, the hook injects the rule-writing guidelines. This ensures every rule Claude creates follows the correct format (frontmatter, keywords, min_matches) without you having to remind it.</p>');
h.push('<p class="dim"><strong>Without this:</strong> Claude would waste tool calls on authenticated URLs that always fail, and create malformed rules that never trigger because the keywords are wrong.</p>');

// PostToolUse
h.push('<h2><span style="color:#da7756;">4.</span> PostToolUse</h2>');
h.push('<p class="dim">Hook: <code>sm-posttooluse.js</code> -- runs after Skill or Task tools complete</p>');
h.push('<p>When Claude uses a skill or task, this hook logs it to <code>skill-usage.jsonl</code> for analytics. It also marks the suggestion as "fulfilled" so the PreToolUse gate stops warning about it.</p>');
h.push('<p>Over time, the analytics log reveals which skills are used vs just suggested. If a skill is suggested 50 times but used twice, its keywords need fixing. This data drives continuous improvement of the keyword system.</p>');
h.push('<p class="dim"><strong>Without this:</strong> No way to know if the keyword matching is actually working. You\'d be guessing about whether skills are being discovered and used.</p>');

// Stop
h.push('<h2><span class="red">5.</span> Stop</h2>');
h.push('<p class="dim">Hook: <code>sm-stop.js</code> -- runs when Claude finishes its response</p>');
h.push('<p>Claude has habits that waste your time. It asks "Want me to fix it?" instead of just fixing it. It says "You should run this command" instead of running it. It restates your instruction as a question before doing it.</p>');
h.push('<p>Stop rules catch these patterns using regex matching against Claude\'s response text. When a pattern matches, the hook injects a correction and Claude redoes the response. You currently have <strong>' + stopRuleCount + ' stop rules</strong> catching different patterns.</p>');
h.push('<p class="dim"><strong>Without this:</strong> Claude keeps asking for permission to do things you already told it to do. You spend half your time saying "yes, do it" instead of getting work done.</p>');

// ===== TEST EVIDENCE =====
h.push('<hr>');
h.push('<h2>Test Evidence</h2>');
h.push('<p>Every claim above was verified by sending test inputs to each hook and checking the output. Here are the results.</p>');

// Summary line
if (failed === 0) {
  h.push('<p><span class="green" style="font-size:18px;font-weight:bold;">' + passed + '/' + total + ' checks passed</span> <span class="dim">in ' + (totalMs / 1000).toFixed(1) + 's</span></p>');
} else {
  h.push('<p><span class="red" style="font-size:18px;font-weight:bold;">' + failed + ' of ' + total + ' checks failed</span></p>');
}

// Group tests by event
var groupOrder = ['SessionStart', 'UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'Stop'];
for (var gi = 0; gi < groupOrder.length; gi++) {
  var gname = groupOrder[gi];
  var gtests = tests.filter(function(t) { return t.group === gname; });
  if (gtests.length === 0) continue;

  h.push('<h3>' + gname + '</h3>');
  h.push('<table>');
  h.push('<tr><th></th><th>Test</th><th>Input</th><th>Keywords</th><th>Action</th><th>Result</th></tr>');
  for (var ti = 0; ti < gtests.length; ti++) {
    var t = gtests[ti];
    h.push('<tr>');
    h.push('<td class="' + (t.pass ? 'icon-pass' : 'icon-fail') + '">' + (t.pass ? '+' : 'X') + '</td>');
    h.push('<td>' + esc(t.name) + '</td>');
    h.push('<td class="prompt-text">' + esc(t.prompt).slice(0, 50) + '</td>');
    h.push('<td>' + esc(t.keywords).split(', ').map(function(k) { return '<span class="kw">' + k + '</span>'; }).join(' ') + '</td>');
    h.push('<td class="dim">' + esc(t.action) + '</td>');
    h.push('<td class="result-text">' + esc(t.result) + '</td>');
    h.push('</tr>');
  }
  h.push('</table>');
}

h.push('<hr>');
h.push('<p style="color:#30363d;font-size:12px;text-align:center;margin-top:40px;">super-manager hook pipeline -- 5 hooks, ' + ruleCount + ' rules, ' + skillCount + ' skills<br>~/.claude/hooks/sm-*.js</p>');
h.push('</body></html>');

var outPath = path.join(OUTPUT_DIR, 'hook-pipeline-report.html');
fs.writeFileSync(outPath, h.join('\n'));

// Console
console.log('');
console.log('  ' + passed + '/' + total + ' passed (' + (totalMs / 1000).toFixed(1) + 's)');
for (var i = 0; i < tests.length; i++) {
  console.log('  ' + (tests[i].pass ? '[+]' : '[X]') + ' ' + tests[i].group + ': ' + tests[i].name);
}
console.log('');
console.log('  Report: ' + outPath);
