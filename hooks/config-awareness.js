#!/usr/bin/env node
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const HOME = process.env.HOME || process.env.USERPROFILE;
const CLAUDE_DIR = path.join(HOME, ".claude");
const LOG_FILE = path.join(CLAUDE_DIR, "hooks", "hooks.log");
const HASH_FILE = path.join(CLAUDE_DIR, "hooks", ".config-hash");
const SETTINGS = path.join(CLAUDE_DIR, "settings.json");
const SKILL_REGISTRY = path.join(CLAUDE_DIR, "hooks", "skill-registry.json");
const HOOK_REGISTRY = path.join(CLAUDE_DIR, "hooks", "hook-registry.json");
const REPORT_FILE = path.join(CLAUDE_DIR, "config-report.md");
const MCP_YAML_PATHS = [
  process.env.MCP_SERVERS_YAML || '',
  path.join(HOME, "mcp", "mcp-manager", "servers.yaml"),
  path.join(HOME, ".claude", "super-manager", "registries", "servers.yaml")
].filter(Boolean);
const SKILLS_DIR = path.join(CLAUDE_DIR, "skills");
const INST_DIR = path.join(CLAUDE_DIR, "instructions");
var NL = String.fromCharCode(10);


function log(level, msg) {
  var ts = new Date().toISOString();
  fs.appendFileSync(LOG_FILE, ts + " [" + level + "] [SessionStart] [config-awareness] " + msg + NL);
}

function safeRead(p) { try { return fs.readFileSync(p, "utf-8"); } catch { return null; } }
function safeJSON(p) { try { return JSON.parse(fs.readFileSync(p, "utf-8")); } catch { return null; } }

function extractHookName(cmd) {
  var segs = cmd.split(String.fromCharCode(34));
  for (var i = 0; i < segs.length; i++) {
    var s = segs[i].trim();
    if (s.endsWith(".js") || s.endsWith(".sh")) return path.basename(s).replace(/[.](js|sh)$/, "");
  }
  return "unknown";
}

function parseServersYaml(content) {
  var servers = {};
  var current = null;
  for (var line of content.split(NL)) {
    var trimmed = line.trim();
    var indent = line.length - line.trimStart().length;
    if (indent === 2 && trimmed.endsWith(":") && !trimmed.includes(" ")) {
      current = trimmed.slice(0, -1);
      servers[current] = { enabled: false, description: "" };
      continue;
    }
    if (!current) continue;
    if (trimmed.startsWith("description:")) servers[current].description = trimmed.split(":").slice(1).join(":").trim();
    if (trimmed.startsWith("enabled:")) servers[current].enabled = trimmed.includes("true");
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
        var name = extractHookName(h.command || "");
        var reg = regMap[name];
        hooks.push({ name: name, event: event, matcher: entry.matcher || "*", async: h.async || false, managed: regNames.has(name), description: reg ? reg.description : "" });
      }
    }
  }
  return hooks;
}

function getMcpServers() {
  var yamlPath = MCP_YAML_PATHS.find(function(p) { return fs.existsSync(p); });
  var managed = {};
  if (yamlPath) managed = parseServersYaml(safeRead(yamlPath) || "");
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
  try { allDirs = fs.readdirSync(SKILLS_DIR).filter(function(d) { try { return fs.statSync(path.join(SKILLS_DIR, d)).isDirectory(); } catch { return false; } }); } catch {}
  var skills = [];
  for (var s of skillReg.skills) {
    skills.push({ id: s.id, name: s.name, enabled: s.enabled || false, managed: true, keywords: (s.keywords || []).slice(0, 5) });
  }
  for (var dir of allDirs) {
    if (!regIds.has(dir)) skills.push({ id: dir, name: dir, enabled: false, managed: false, keywords: [] });
  }
  return skills;
}


function getInstructions() {
  var instructions = [];
  try {
    var files = fs.readdirSync(INST_DIR).filter(function(f) { return f.endsWith(".md") && f !== "README.md"; });
    for (var f of files) {
      var content = fs.readFileSync(path.join(INST_DIR, f), "utf-8");
      if (!content.startsWith("---")) continue;
      var end = content.indexOf("---", 3);
      if (end === -1) continue;
      var yaml = content.substring(3, end).trim();
      var meta = { file: f };
      for (var line of yaml.split(NL)) {
        var col = line.indexOf(":");
        if (col === -1) continue;
        var key = line.substring(0, col).trim();
        var val = line.substring(col + 1).trim();
        if (val.startsWith("[") && val.endsWith("]")) {
          meta[key] = val.slice(1, -1).split(",").map(function(s) { return s.trim(); });
        } else { meta[key] = val; }
      }
      if (meta.id) instructions.push(meta);
    }
  } catch {}
  return instructions;
}

function computeHash(hooks, servers, skills, instructions) {
  // Normalize to minimal fields for hash stability (must match configCheck in tool-reminder.js)
  var h = hooks.map(function(x) { return { event: x.event, matcher: x.matcher, name: x.name, async: x.async }; });
  var m = servers.map(function(x) { return { name: x.name, enabled: x.enabled }; });
  var s = skills.map(function(x) { return { id: x.id, enabled: x.enabled }; });
  var i = (instructions || []).map(function(x) { return { id: x.id }; });
  return crypto.createHash("md5").update(JSON.stringify({ hooks: h, servers: m, skills: s, instructions: i })).digest("hex");
}

function formatContextSummary(hooks, servers, skills, instructions) {
  var out = ["<system-reminder>", "# Active Claude Configuration", ""];
  out.push("## Hooks (" + hooks.length + ")");
  var byEvent = {};
  for (var h of hooks) { if (!byEvent[h.event]) byEvent[h.event] = []; byEvent[h.event].push(h); }
  for (var ev of Object.keys(byEvent)) {
    out.push("### " + ev);
    for (var hk of byEvent[ev]) {
      var flags = [];
      if (hk.matcher !== "*") flags.push("matcher=" + hk.matcher);
      if (hk.async) flags.push("async");
      if (!hk.managed) flags.push("UNMANAGED");
      out.push("- " + hk.name + (flags.length ? " (" + flags.join(", ") + ")" : ""));
    }
  }
  var enabledMcp = servers.filter(function(s) { return s.enabled; });
  if (enabledMcp.length > 0) {
    out.push("");
    out.push("## MCP Servers (" + enabledMcp.length + " enabled)");
    for (var m of enabledMcp) out.push("- " + m.name + (!m.managed ? " (UNMANAGED)" : ""));
  }
  var enabledSkills = skills.filter(function(s) { return s.enabled; });
  if (enabledSkills.length > 0) {
    out.push("");
    out.push("## Skills (" + enabledSkills.length + " enabled)");
    for (var s of enabledSkills) out.push("- " + s.id + (!s.managed ? " (UNMANAGED)" : ""));
  }
  out.push("");

  if (instructions.length > 0) {
    out.push("");
    out.push("## Instructions (" + instructions.length + " files)");
    for (var inst of instructions) out.push("- " + inst.id + ": " + (inst.description || ""));
  }
  out.push("");
  out.push("Full report: ~/.claude/config-report.md");
  out.push("</system-reminder>");
  return out.join(NL);
}

function writeReport(hooks, servers, skills, instructions, hash) {
  var now = new Date().toISOString().replace("T", " ").slice(0, 19);
  var mH = hooks.filter(function(h) { return h.managed; });
  var uH = hooks.filter(function(h) { return !h.managed; });
  var mM = servers.filter(function(s) { return s.managed; });
  var uM = servers.filter(function(s) { return !s.managed; });
  var mS = skills.filter(function(s) { return s.managed; });
  var uS = skills.filter(function(s) { return !s.managed; });
  var o = [];
  o.push("# Claude Configuration Report");
  o.push("");
  o.push("**Last updated:** " + now + " UTC");
  o.push("**Config hash:** " + hash.slice(0, 8));
  o.push("");
  o.push("| Manager | Managed | Unmanaged | Total |");
  o.push("|---------|---------|-----------|-------|");
  o.push("| Hook Manager | " + mH.length + " | " + uH.length + " | " + hooks.length + " |");
  o.push("| MCP Manager | " + mM.length + " | " + uM.length + " | " + servers.length + " |");
  o.push("| Skill Registry | " + mS.length + " | " + uS.length + " | " + skills.length + " |");
  o.push("| Instruction Manager | " + instructions.length + " | 0 | " + instructions.length + " |");
  o.push("");
  o.push("---");
  o.push("");
  o.push("## Hook Manager (" + hooks.length + ")");
  o.push("");
  o.push("Registry: hook-registry.json");
  o.push("");
  if (mH.length > 0) {
    o.push("### Managed Hooks (" + mH.length + ")");
    o.push("");
    o.push("| Hook | Event | Matcher | Async | Description |");
    o.push("|------|-------|---------|-------|-------------|");
    for (var h of mH) o.push("| " + h.name + " | " + h.event + " | " + h.matcher + " | " + (h.async ? "yes" : "no") + " | " + h.description + " |");
    o.push("");
  }
  if (uH.length > 0) {
    o.push("### Unmanaged Hooks (" + uH.length + ")");
    o.push("");
    o.push("| Hook | Event | Matcher | Note |");
    o.push("|------|-------|---------|------|");
    for (var h of uH) o.push("| " + h.name + " | " + h.event + " | " + h.matcher + " | Not in hook-registry.json |");
    o.push("");
  }
  o.push("---");
  o.push("");
  o.push("## MCP Manager (" + servers.length + ")");
  o.push("");
  o.push("Registry: mcp-manager/servers.yaml");
  o.push("");
  if (mM.length > 0) {
    o.push("### Managed Servers (" + mM.length + ")");
    o.push("");
    o.push("| Server | Enabled | Description |");
    o.push("|--------|---------|-------------|");
    for (var m of mM) o.push("| " + m.name + " | " + (m.enabled ? "yes" : "no") + " | " + m.description + " |");
    o.push("");
  }
  if (uM.length > 0) {
    o.push("### Unmanaged Servers (" + uM.length + ")");
    o.push("");
    for (var m of uM) o.push("- " + m.name + " (not in servers.yaml)");
    o.push("");
  }
  o.push("---");
  o.push("");
  o.push("## Skill Registry (" + skills.length + ")");
  o.push("");
  o.push("Registry: skill-registry.json");
  o.push("");
  if (mS.length > 0) {
    o.push("### Managed Skills (" + mS.length + ")");
    o.push("");
    o.push("| Skill | Name | Enabled | Keywords |");
    o.push("|-------|------|---------|----------|");
    for (var s of mS) o.push("| " + s.id + " | " + s.name + " | " + (s.enabled ? "yes" : "no") + " | " + s.keywords.join(", ") + " |");
    o.push("");
  }
  if (uS.length > 0) {
    o.push("### Unmanaged Skills (" + uS.length + ")");
    o.push("");
    for (var s of uS) o.push("- " + s.id + "/ (in ~/.claude/skills/ but not in skill-registry.json)");
    o.push("");
  }

  o.push("---");
  o.push("");
  o.push("## Instruction Manager (" + instructions.length + ")");
  o.push("");
  o.push("Registry: ~/.claude/instructions/ (self-describing .md files with YAML frontmatter)");
  o.push("");
  if (instructions.length > 0) {
    o.push("| ID | Keywords | Tools | Description |");
    o.push("|----|----------|-------|-------------|");
    for (var inst of instructions) {
      var kw = (inst.keywords || []).slice(0, 4).join(", ");
      var tl = (inst.tools || []).join(", ") || "none";
      o.push("| " + inst.id + " | " + kw + " | " + tl + " | " + (inst.description || "") + " |");
    }
    o.push("");
  }

  o.push("---");
  o.push("");
  o.push("## Change Log");
  o.push("");
  var newEntry = "- " + now + " - Session start (hash=" + hash.slice(0,8) + ", " + hooks.length + "h/" + servers.length + "m/" + skills.length + "s)";
  o.push(newEntry);
  try {
    var old = fs.readFileSync(REPORT_FILE, "utf-8");
    var clIdx = old.indexOf("## Change Log");
    if (clIdx !== -1) {
      var after = old.substring(clIdx + "## Change Log".length).trim();
      var entries = after.split(NL).filter(function(l) { return l.startsWith("- "); }).slice(0, 19);
      for (var e of entries) o.push(e);
    }
  } catch {}
  o.push("");
  fs.writeFileSync(REPORT_FILE, o.join(NL));
}

function ensureToolRouting() {
  // Auto-inject Tool Routing into CLAUDE.md if missing
  // WHY: Claude sees 30+ skills. Without routing table, it guesses wrong.
  var claudeMd = path.join(HOME, ".claude", "CLAUDE.md");
  var script = path.join(HOME, ".claude", "super-manager", "inject_routing.py");
  try {
    if (!fs.existsSync(script)) return;
    var content = safeRead(claudeMd);
    if (!content || content.indexOf("## Tool Routing (managed by super-manager)") !== -1) return;
    require("child_process").execSync("python " + JSON.stringify(script), { stdio: "pipe", timeout: 5000 });
    log("INFO", "auto-injected Tool Routing into CLAUDE.md");
  } catch (e) { log("WARN", "routing inject failed: " + e.message); }
}

async function main() {
  var input = ""; for await (var chunk of process.stdin) input += chunk;
  try {
    var hooks = getHooks();
    var servers = getMcpServers();
    var skills = getSkills();
    var instructions = getInstructions();
    var hash = computeHash(hooks, servers, skills, instructions);
    fs.writeFileSync(HASH_FILE, hash);
    writeReport(hooks, servers, skills, instructions, hash);
    ensureToolRouting();
    log("INFO", "report: " + hooks.length + "h/" + servers.length + "m/" + skills.length + "s/" + instructions.length + "i hash=" + hash.slice(0,8));
    console.log(formatContextSummary(hooks, servers, skills, instructions));
  } catch (e) { log("ERROR", e.message); }
  process.exit(0);
}
main().catch(function() { process.exit(0); });
