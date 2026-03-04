#!/usr/bin/env node
/**
 * @hook sm-sessionstart
 * @event SessionStart
 * @matcher *
 * @description Super-manager SessionStart entry point. Modules:
 *   1. config-awareness: scans registries, writes report, injects summary
 *   2. skill-health: checks hook files exist, auto-remediates, enriches keywords
 */
var fs = require('fs');
var path = require('path');
var crypto = require('crypto');

var HOME = process.env.HOME || process.env.USERPROFILE;
var CLAUDE_DIR = path.join(HOME, '.claude');
var LOG_FILE = path.join(CLAUDE_DIR, 'hooks', 'hooks.log');
var HASH_FILE = path.join(CLAUDE_DIR, 'hooks', '.config-hash');
var SETTINGS = path.join(CLAUDE_DIR, 'settings.json');
var SKILL_REGISTRY = path.join(CLAUDE_DIR, 'hooks', 'skill-registry.json');
var HOOK_REGISTRY = path.join(CLAUDE_DIR, 'hooks', 'hook-registry.json');
var REPORT_FILE = path.join(CLAUDE_DIR, 'config-report.md');
var SKILLS_DIR = path.join(CLAUDE_DIR, 'skills');
var RULES_DIR = path.join(CLAUDE_DIR, 'rules');
var SKILL_USAGE_LOG = path.join(HOME, '.claude', 'logs', 'skill-usage.log');
var MCP_YAML_PATHS = [
  process.env.MCP_SERVERS_YAML || '',
  path.join(HOME, 'mcp', 'mcp-manager', 'servers.yaml'),
  path.join(HOME, '.claude', 'super-manager', 'registries', 'servers.yaml')
].filter(Boolean);
var NL = String.fromCharCode(10);

function log(module, level, msg) {
  var ts = new Date().toISOString();
  try { fs.appendFileSync(LOG_FILE, ts + ' [' + level + '] [SessionStart] [sm:' + module + '] ' + msg + NL); } catch (e) {}
}

function safeRead(p) { try { return fs.readFileSync(p, 'utf-8'); } catch (e) { return null; } }
function safeJSON(p) { try { return JSON.parse(fs.readFileSync(p, 'utf-8')); } catch (e) { return null; } }

// ===== MODULE: config-awareness =====
// Scans all registries, writes report, outputs context summary

function extractHookName(cmd) {
  var segs = cmd.split(String.fromCharCode(34));
  for (var i = 0; i < segs.length; i++) {
    var s = segs[i].trim();
    if (s.endsWith('.js') || s.endsWith('.sh')) return path.basename(s).replace(/[.](js|sh)$/, '');
  }
  return 'unknown';
}

function parseServersYaml(content) {
  var servers = {};
  var current = null;
  for (var line of content.split(NL)) {
    var trimmed = line.trim();
    var indent = line.length - line.trimStart().length;
    if (indent === 2 && trimmed.endsWith(':') && !trimmed.includes(' ')) {
      current = trimmed.slice(0, -1);
      servers[current] = { enabled: false, description: '' };
      continue;
    }
    if (!current) continue;
    if (trimmed.startsWith('description:')) servers[current].description = trimmed.split(':').slice(1).join(':').trim();
    if (trimmed.startsWith('enabled:')) servers[current].enabled = trimmed.includes('true');
  }
  return servers;
}

function getHooks() {
  var settings = safeJSON(SETTINGS) || {};
  var hookReg = safeJSON(HOOK_REGISTRY) || { hooks: [] };
  var regNames = new Set(hookReg.hooks.map(function(h) { return h.name; }));
  var regMap = {};
  for (var rh of hookReg.hooks) regMap[rh.name] = rh;
  var hooks = [];
  for (var event of Object.keys((settings.hooks || {}))) {
    for (var entry of settings.hooks[event]) {
      for (var h of (entry.hooks || [])) {
        var name = extractHookName(h.command || '');
        var reg = regMap[name];
        hooks.push({ name: name, event: event, matcher: entry.matcher || '*', async: h.async || false, managed: regNames.has(name), description: reg ? reg.description : '' });
      }
    }
  }
  return hooks;
}

function getMcpServers() {
  var yamlPath = MCP_YAML_PATHS.find(function(p) { return fs.existsSync(p); });
  var managed = {};
  if (yamlPath) managed = parseServersYaml(safeRead(yamlPath) || '');
  var servers = [];
  for (var name of Object.keys(managed)) {
    servers.push({ name: name, enabled: managed[name].enabled, managed: true, description: managed[name].description });
  }
  return servers;
}

function getSkills() {
  var skillReg = safeJSON(SKILL_REGISTRY) || { skills: [] };
  var regIds = new Set(skillReg.skills.map(function(s) { return s.id; }));
  var allDirs = [];
  try { allDirs = fs.readdirSync(SKILLS_DIR).filter(function(d) { try { return fs.statSync(path.join(SKILLS_DIR, d)).isDirectory(); } catch (e) { return false; } }); } catch (e) {}
  var skills = [];
  for (var s of skillReg.skills) {
    skills.push({ id: s.id, name: s.name, enabled: s.enabled || false, managed: true, keywords: (s.keywords || []).slice(0, 5) });
  }
  for (var dir of allDirs) {
    if (!regIds.has(dir)) skills.push({ id: dir, name: dir, enabled: false, managed: false, keywords: [] });
  }
  return skills;
}

function getRules() {
  var rules = [];
  try {
    var upsDir = path.join(RULES_DIR, 'UserPromptSubmit');
    if (!fs.existsSync(upsDir)) return rules;
    var files = fs.readdirSync(upsDir).filter(function(f) { return f.endsWith('.md') && f !== 'README.md'; });
    for (var f of files) {
      var content = fs.readFileSync(path.join(upsDir, f), 'utf-8');
      if (!content.startsWith('---')) continue;
      var end = content.indexOf('---', 3);
      if (end === -1) continue;
      var yaml = content.substring(3, end).trim();
      var meta = { file: f };
      for (var line of yaml.split(NL)) {
        var col = line.indexOf(':');
        if (col === -1) continue;
        var key = line.substring(0, col).trim();
        var val = line.substring(col + 1).trim();
        if (val.startsWith('[') && val.endsWith(']')) {
          meta[key] = val.slice(1, -1).split(',').map(function(s) { return s.trim(); });
        } else { meta[key] = val; }
      }
      if (meta.id) rules.push(meta);
    }
  } catch (e) {}
  return rules;
}

function computeHash(hooks, servers, skills, rules) {
  var h = hooks.map(function(x) { return { event: x.event, matcher: x.matcher, name: x.name, async: x.async }; });
  var m = servers.map(function(x) { return { name: x.name, enabled: x.enabled }; });
  var s = skills.map(function(x) { return { id: x.id, enabled: x.enabled }; });
  var i = (rules || []).map(function(x) { return { id: x.id }; });
  return crypto.createHash('md5').update(JSON.stringify({ hooks: h, servers: m, skills: s, rules: i })).digest('hex');
}

function formatContextSummary(hooks, servers, skills, rules) {
  var out = ['<system-reminder>', '# Active Claude Configuration', ''];
  out.push('## Hooks (' + hooks.length + ')');
  var byEvent = {};
  for (var h of hooks) { if (!byEvent[h.event]) byEvent[h.event] = []; byEvent[h.event].push(h); }
  for (var ev of Object.keys(byEvent)) {
    out.push('### ' + ev);
    for (var hk of byEvent[ev]) {
      var flags = [];
      if (hk.matcher !== '*') flags.push('matcher=' + hk.matcher);
      if (hk.async) flags.push('async');
      if (!hk.managed) flags.push('UNMANAGED');
      out.push('- ' + hk.name + (flags.length ? ' (' + flags.join(', ') + ')' : ''));
    }
  }
  var enabledSkills = skills.filter(function(s) { return s.enabled; });
  if (enabledSkills.length > 0) {
    out.push('');
    out.push('## Skills (' + enabledSkills.length + ' enabled)');
    for (var s of enabledSkills) out.push('- ' + s.id);
  }
  out.push('');
  out.push('Full report: ~/.claude/config-report.md');
  out.push('</system-reminder>');
  return out.join(NL);
}

function writeReport(hooks, servers, skills, rules, hash) {
  var now = new Date().toISOString().replace('T', ' ').slice(0, 19);
  var mH = hooks.filter(function(h) { return h.managed; });
  var uH = hooks.filter(function(h) { return !h.managed; });
  var mM = servers.filter(function(s) { return s.managed; });
  var uM = servers.filter(function(s) { return !s.managed; });
  var mS = skills.filter(function(s) { return s.managed; });
  var uS = skills.filter(function(s) { return !s.managed; });
  var o = [];
  o.push('# Claude Configuration Report');
  o.push('');
  o.push('**Last updated:** ' + now + ' UTC');
  o.push('**Config hash:** ' + hash.slice(0, 8));
  o.push('');
  o.push('| Manager | Managed | Unmanaged | Total |');
  o.push('|---------|---------|-----------|-------|');
  o.push('| Hook Manager | ' + mH.length + ' | ' + uH.length + ' | ' + hooks.length + ' |');
  o.push('| MCP Manager | ' + mM.length + ' | ' + uM.length + ' | ' + servers.length + ' |');
  o.push('| Skill Registry | ' + mS.length + ' | ' + uS.length + ' | ' + skills.length + ' |');
  o.push('| Rule Manager | ' + rules.length + ' | 0 | ' + rules.length + ' |');
  o.push('');
  o.push('---');
  o.push('');
  // Hook details
  o.push('## Hooks (' + hooks.length + ')');
  o.push('');
  o.push('| Hook | Event | Matcher | Managed | Description |');
  o.push('|------|-------|---------|---------|-------------|');
  for (var h of hooks) o.push('| ' + h.name + ' | ' + h.event + ' | ' + h.matcher + ' | ' + (h.managed ? 'yes' : 'no') + ' | ' + h.description + ' |');
  o.push('');
  // MCP details
  o.push('## MCP Servers (' + servers.length + ')');
  o.push('');
  o.push('| Server | Enabled | Description |');
  o.push('|--------|---------|-------------|');
  for (var m of servers) o.push('| ' + m.name + ' | ' + (m.enabled ? 'yes' : 'no') + ' | ' + m.description + ' |');
  o.push('');
  // Skill details
  o.push('## Skills (' + skills.length + ')');
  o.push('');
  o.push('| Skill | Enabled | Keywords |');
  o.push('|-------|---------|----------|');
  for (var s of skills) o.push('| ' + s.id + ' | ' + (s.enabled ? 'yes' : 'no') + ' | ' + (s.keywords || []).join(', ') + ' |');
  o.push('');
  // Rule details
  o.push('## Rules (' + rules.length + ')');
  o.push('');
  o.push('| ID | Keywords | Description |');
  o.push('|----|----------|-------------|');
  for (var r of rules) o.push('| ' + r.id + ' | ' + ((r.keywords || []).slice(0, 4).join(', ')) + ' | ' + (r.description || '') + ' |');
  o.push('');
  // Change log
  o.push('---');
  o.push('');
  o.push('## Change Log');
  o.push('');
  var newEntry = '- ' + now + ' - Session start (hash=' + hash.slice(0, 8) + ', ' + hooks.length + 'h/' + servers.length + 'm/' + skills.length + 's/' + rules.length + 'r)';
  o.push(newEntry);
  try {
    var old = fs.readFileSync(REPORT_FILE, 'utf-8');
    var clIdx = old.indexOf('## Change Log');
    if (clIdx !== -1) {
      var after = old.substring(clIdx + '## Change Log'.length).trim();
      var entries = after.split(NL).filter(function(l) { return l.startsWith('- '); }).slice(0, 19);
      for (var e of entries) o.push(e);
    }
  } catch (e) {}
  o.push('');
  fs.writeFileSync(REPORT_FILE, o.join(NL));
}

function ensureToolRouting() {
  var claudeMd = path.join(HOME, '.claude', 'CLAUDE.md');
  var script = path.join(HOME, '.claude', 'super-manager', 'inject_routing.py');
  try {
    if (!fs.existsSync(script)) return;
    var content = safeRead(claudeMd);
    if (!content || content.indexOf('## Tool Routing (managed by super-manager)') !== -1) return;
    require('child_process').execSync('python ' + JSON.stringify(script), { stdio: 'pipe', timeout: 5000 });
    log('config', 'INFO', 'auto-injected Tool Routing into CLAUDE.md');
  } catch (e) { log('config', 'WARN', 'routing inject failed: ' + e.message); }
}

function moduleConfigAwareness() {
  try {
    var hooks = getHooks();
    var servers = getMcpServers();
    var skills = getSkills();
    var rules = getRules();
    var hash = computeHash(hooks, servers, skills, rules);
    fs.writeFileSync(HASH_FILE, hash);
    writeReport(hooks, servers, skills, rules, hash);
    ensureToolRouting();
    log('config', 'INFO', 'report: ' + hooks.length + 'h/' + servers.length + 'm/' + skills.length + 's/' + rules.length + 'r hash=' + hash.slice(0, 8));
    return formatContextSummary(hooks, servers, skills, rules);
  } catch (e) {
    log('config', 'ERROR', e.message);
    return null;
  }
}

// ===== MODULE: skill-health =====
// Checks hook files exist, auto-remediates, enriches frontmatter keywords

function moduleSkillHealth() {
  try {
    var HOOKS_DIR = path.join(CLAUDE_DIR, 'hooks');

    // 1. Check required hook files exist
    var required = ['sm-posttooluse.js', 'sm-sessionstart.js'];
    var issues = [];
    for (var r of required) {
      if (!fs.existsSync(path.join(HOOKS_DIR, r))) issues.push('missing:' + r);
    }

    // 2. Check settings.json has hooks registered
    try {
      var sStr = fs.readFileSync(SETTINGS, 'utf-8');
      for (var r of required) {
        if (sStr.indexOf(r) === -1) issues.push('unregistered:' + r);
      }
    } catch (e) {}

    if (issues.length > 0) {
      log('health', 'WARN', 'issues: ' + issues.join(', '));
    } else {
      log('health', 'INFO', required.length + ' hooks verified');
    }

    // 3. Check frontmatter keyword quality
    if (fs.existsSync(SKILLS_DIR)) {
      var entries = fs.readdirSync(SKILLS_DIR);
      var missing = [];
      for (var entry of entries) {
        var dirPath = path.join(SKILLS_DIR, entry);
        try { if (!fs.statSync(dirPath).isDirectory()) continue; } catch (e) { continue; }
        if (entry === 'archive' || entry.endsWith('.zip')) continue;
        var skillMd = path.join(dirPath, 'SKILL.md');
        if (!fs.existsSync(skillMd)) continue;
        var content = fs.readFileSync(skillMd, 'utf-8');
        var hasKw = false;
        if (content.startsWith('---')) {
          var endIdx = content.indexOf('---', 3);
          if (endIdx !== -1) {
            var fm = content.substring(3, endIdx);
            hasKw = fm.indexOf('keywords:') !== -1;
          }
        }
        if (!hasKw) missing.push(entry);
      }
      if (missing.length > 0) {
        log('health', 'WARN', 'skills missing keywords: ' + missing.join(', '));
        // Auto-enrich if skill-manager setup.js exists
        var setupPath = path.join(SKILLS_DIR, 'skill-manager', 'setup.js');
        if (fs.existsSync(setupPath)) {
          try {
            delete require.cache[require.resolve(setupPath)];
            var setup = require(setupPath);
            var inv = setup.scanAllSkills();
            setup.enrichAllSkills(inv);
            if (typeof setup.buildSkillRegistry === 'function') setup.buildSkillRegistry(inv, []);
            log('health', 'INFO', 'enriched ' + inv.length + ' skills');
          } catch (e) {}
        }
      }
    }

    // 4. Check mcp-manager registration
    try {
      var mcpSetupPath = path.join(SKILLS_DIR, 'mcp-manager', 'setup.js');
      if (fs.existsSync(mcpSetupPath)) {
        delete require.cache[require.resolve(mcpSetupPath)];
        var mcpSetup = require(mcpSetupPath);
        if (typeof mcpSetup.checkMcpRegistration === 'function') {
          var mcpCheck = mcpSetup.checkMcpRegistration();
          if (!mcpCheck.registered && typeof mcpSetup.ensureMcpRegistration === 'function') {
            var mcpResult = mcpSetup.ensureMcpRegistration();
            if (mcpResult.action === 'registered') log('health', 'INFO', 'mcp auto-registered: ' + mcpResult.buildPath);
          }
        }
      }
    } catch (e) {}
  } catch (e) {
    log('health', 'ERROR', e.message);
  }
}

// ===== MAIN =====

async function main() {
  var input = ''; for await (var chunk of process.stdin) input += chunk;

  // Module 1: config-awareness (outputs context summary)
  var summary = moduleConfigAwareness();
  if (summary) console.log(summary);

  // Module 2: skill-health (silent, logs only)
  moduleSkillHealth();

  process.exit(0);
}

main().catch(function() { process.exit(0); });
