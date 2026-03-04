#!/usr/bin/env node
/**
 * @hook tool-reminder
 * @event UserPromptSubmit
 * @matcher *
 * @description Unified context injector with 3 modules:
 *   - claudemd: Injects global ~/.claude/CLAUDE.md
 *   - skill: Injects skill docs based on keyword matching
 *   - mcp: Suggests MCP servers based on keyword matching
 *   Plus observability: TUI output + log + status-line-cache
 */
const fs = require('fs');
const path = require('path');

const HOOK_NAME = 'skill-mcp-claudemd-injector';
const EVENT_TYPE = 'UserPromptSubmit';
const HOME = process.env.HOME || process.env.USERPROFILE;
const LOG_FILE = path.join(HOME, '.claude', 'hooks', 'hooks.log');
const STATE_DIR = path.join(HOME, '.claude', 'super-manager', 'state');
const STATE_FILE = path.join(STATE_DIR, 'super-manager-pending-suggestions.json');
const STATUS_CACHE = path.join(HOME, '.claude', 'super-manager', 'state', 'status-line-cache.json');

// Logging with module name
function log(module, level, msg) {
  const ts = new Date().toISOString();
  fs.appendFileSync(LOG_FILE, `${ts} [${level}] [${EVENT_TYPE}] [${HOOK_NAME}:${module}] ${msg}\n`);
}

// ===== MODULE: claudemd =====
// DISABLED: Claude Code natively loads ~/.claude/CLAUDE.md on every prompt.
// Injecting it again doubled context (~13KB per prompt). Global CLAUDE.md
// now contains only language prefs + general ops. All behavioral rules
// live in ~/.claude/rules/ and are keyword-matched by moduleRuleLoader.
function moduleClaudeMd() {
  log('claudemd', 'DEBUG', 'skipped - Claude Code loads CLAUDE.md natively');
  return null;
}

// ===== MODULE: skill =====
let lastMatchedSkills = [];
function moduleSkill(prompt) {
  lastMatchedSkills = [];
  const registryPath = path.join(HOME, '.claude', 'hooks', 'skill-registry.json');
  try {
    if (!fs.existsSync(registryPath)) {
      log('skill', 'DEBUG', 'no skill-registry.json');
      return null;
    }

    const registry = JSON.parse(fs.readFileSync(registryPath, 'utf-8'));
    const matched = [];

    for (const skill of registry.skills || []) {
      if (!skill.enabled) continue;
      let hitKeyword = null;
      const hit = (skill.keywords || []).some(kw => {
        if (prompt.includes(kw.toLowerCase())) { hitKeyword = kw; return true; }
        return false;
      });
      if (hit) {
        matched.push(skill);
        lastMatchedSkills.push({ id: skill.id, reason: hitKeyword });
      }
    }

    if (matched.length === 0) {
      log('skill', 'DEBUG', 'no skills matched');
      return null;
    }

    // DECISION (2026-02-18): Stop injecting skill content. Let Claude's native
    // skill matching use frontmatter keywords instead. Skill tool calls become
    // visible in output. Registry still used for observability/logging/enforcement.
    log('skill', 'INFO', `matched ${matched.length} skills (no inject): ${matched.map(s => s.id).join(', ')}`);
    return null;
  } catch (e) {
    log('skill', 'ERROR', `failed: ${e.message}`);
  }
  return null;
}

// ===== MODULE: mcp =====
let lastMatchedMcps = [];
function moduleMcp(prompt) {
  lastMatchedMcps = [];
  const serversPaths = [
    path.join(HOME, 'OneDrive - TrendMicro', 'Documents', 'ProjectsCL', 'MCP', 'mcp-manager', 'servers.yaml'),
    path.join(HOME, 'mcp', 'mcp-manager', 'servers.yaml')
  ];

  const serversPath = serversPaths.find(p => fs.existsSync(p));
  if (!serversPath) {
    log('mcp', 'DEBUG', 'no servers.yaml found');
    return null;
  }

  try {
    const content = fs.readFileSync(serversPath, 'utf-8');
    const servers = parseServersYaml(content);
    const matched = [];

    for (const [name, server] of Object.entries(servers)) {
      if (!server.enabled) continue;
      // Only match on keywords, NOT tags. Tags are categorization metadata, not user intent.
      const terms = (server.keywords || []).map(t => t.toLowerCase());
      let mcpHitKeyword = null;
      if (terms.some(t => { if (prompt.includes(t)) { mcpHitKeyword = t; return true; } return false; })) {
        matched.push({ name, description: server.description || name });
        lastMatchedMcps.push({ name, reason: mcpHitKeyword });
      }
    }

    if (matched.length === 0) {
      log('mcp', 'DEBUG', 'no MCP servers matched');
      return null;
    }

    log('mcp', 'INFO', `suggested ${matched.length} MCPs: ${matched.map(s => s.name).join(', ')}`);
    const lines = ['--- MCP SERVER SUGGESTION ---', 'Relevant MCP servers for this task:'];
    for (const s of matched) lines.push(`- ${s.name}: ${s.description}`);
    lines.push('Use mcp__mcp-manager tools to start/call these.');
    lines.push('--- END MCP SUGGESTION ---');
    return lines.join('\n');
  } catch (e) {
    log('mcp', 'ERROR', `failed: ${e.message}`);
  }
  return null;
}

// Simple YAML parser for servers.yaml
function parseServersYaml(content) {
  const servers = {};
  let current = null, inKw = false, inTags = false;

  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    const indent = line.length - line.trimStart().length;

    if (indent === 2 && trimmed.endsWith(':') && !trimmed.includes(' ')) {
      current = trimmed.slice(0, -1);
      servers[current] = { keywords: [], tags: [], enabled: false, description: '' };
      inKw = inTags = false;
      continue;
    }
    if (!current) continue;

    if (trimmed.startsWith('description:')) {
      servers[current].description = trimmed.split(':').slice(1).join(':').trim();
    } else if (trimmed.startsWith('enabled:')) {
      servers[current].enabled = trimmed.includes('true');
    } else if (trimmed === 'keywords:') { inKw = true; inTags = false; }
    else if (trimmed === 'tags:') { inTags = true; inKw = false; }
    else if (trimmed.startsWith('- ') && (inKw || inTags)) {
      const val = trimmed.slice(2).trim();
      if (inKw) servers[current].keywords.push(val);
      if (inTags) servers[current].tags.push(val);
    } else if (!trimmed.startsWith('-') && trimmed.includes(':')) {
      inKw = inTags = false;
    }
  }
  return servers;
}

// ===== MODULE: ruleLoader =====
let lastMatchedRules = [];
function moduleRuleLoader(prompt) {
  lastMatchedRules = [];
  var INST_DIR = path.join(HOME, ".claude", "rules");
  var LOG_FILE = path.join(INST_DIR, "loader.log");
  var CACHE_FILE = path.join(INST_DIR, ".loaded-cache");

  function instLog(msg) {
    var ts = new Date().toISOString();
    try { fs.appendFileSync(LOG_FILE, ts + " " + msg + String.fromCharCode(10)); } catch {}
  }

  function parseFM(content) {
    if (!content.startsWith("---")) return null;
    var endIdx = content.indexOf("---", 3);
    if (endIdx === -1) return null;
    var yaml = content.substring(3, endIdx).trim();
    var meta = {};
    var yamlLines = yaml.split(String.fromCharCode(10));
    var currentListKey = null;
    for (var j = 0; j < yamlLines.length; j++) {
      var ln = yamlLines[j];
      var trimmed = ln.trim();
      // Handle multi-line YAML list items (e.g. "  - atlassian.net")
      if (trimmed.startsWith("- ") && currentListKey) {
        if (!Array.isArray(meta[currentListKey])) meta[currentListKey] = [];
        meta[currentListKey].push(trimmed.slice(2).trim());
        continue;
      }
      currentListKey = null;
      var col = ln.indexOf(":");
      if (col === -1) continue;
      var key = ln.substring(0, col).trim();
      var val = ln.substring(col + 1).trim();
      if (val.startsWith("[") && val.endsWith("]")) {
        meta[key] = val.slice(1, -1).split(",").map(function(s) { return s.trim(); });
      } else if (val === "") {
        // Empty value after colon -- next lines may be list items
        currentListKey = key;
      } else { meta[key] = val; }
    }
    meta.body = content.substring(endIdx + 3).trim();
    return meta;
  }

  try {
    if (!fs.existsSync(INST_DIR)) return null;
    var cache;
    try { cache = JSON.parse(fs.readFileSync(CACHE_FILE, "utf-8")); }
    catch { cache = { loaded: [], sessionTs: Date.now() }; }

    if (!cache.sessionTs || (Date.now() - cache.sessionTs) > 7200000) {
      cache = { loaded: [], sessionTs: Date.now() };
    }

    // Scan top-level AND subdirectories (e.g. UserPromptSubmit/, Stop/) for .md files
    var files = [];
    var topEntries = fs.readdirSync(INST_DIR);
    for (var ei = 0; ei < topEntries.length; ei++) {
      var entryPath = path.join(INST_DIR, topEntries[ei]);
      try {
        var stat = fs.statSync(entryPath);
        if (stat.isFile() && topEntries[ei].endsWith(".md") && topEntries[ei] !== "README.md") {
          files.push(entryPath);
        } else if (stat.isDirectory() && topEntries[ei] === "UserPromptSubmit") {
          var subFiles = fs.readdirSync(entryPath).filter(function(f) { return f.endsWith(".md") && f !== "README.md"; });
          for (var si = 0; si < subFiles.length; si++) {
            files.push(path.join(entryPath, subFiles[si]));
          }
        }
      } catch {}
    }

    // Scan MCP server rules/ directories (collocated rules that migrate with the MCP)
    var MCP_YAML_PATHS = [
      path.join(HOME, "OneDrive - TrendMicro", "Documents", "ProjectsCL", "MCP", "mcp-manager", "servers.yaml"),
      path.join(HOME, "mcp", "mcp-manager", "servers.yaml")
    ];
    var mcpYaml = MCP_YAML_PATHS.find(function(p) { try { return fs.existsSync(p); } catch { return false; } });
    if (mcpYaml) {
      var mcpRoot = path.dirname(path.dirname(mcpYaml)); // up from mcp-manager/ to MCP/
      try {
        var mcpDirs = fs.readdirSync(mcpRoot).filter(function(d) {
          return d.startsWith("mcp-");
        });
        for (var mi = 0; mi < mcpDirs.length; mi++) {
          var rulesDir = path.join(mcpRoot, mcpDirs[mi], "rules");
          try {
            if (!fs.existsSync(rulesDir)) continue;
            var ruleFiles = fs.readdirSync(rulesDir).filter(function(f) { return f.endsWith(".md") && f !== "README.md"; });
            for (var ri = 0; ri < ruleFiles.length; ri++) {
              files.push(path.join(rulesDir, ruleFiles[ri]));
            }
            if (ruleFiles.length > 0) {
              instLog("[MCP-RULES] scanned " + mcpDirs[mi] + "/rules/ -> " + ruleFiles.length + " rules");
            }
          } catch {}
        }
      } catch (mcpErr) {
        instLog("[MCP-RULES] scan error: " + mcpErr.message);
      }
    }
    var promptLower = (prompt || "").toLowerCase();
    var outputs = [];

    for (var fi = 0; fi < files.length; fi++) {
      var content = fs.readFileSync(files[fi], "utf-8");
      var meta = parseFM(content);
      if (!meta || !meta.keywords) continue;

      // Derive id from frontmatter or filename (e.g. "confluence-url-routing.md" -> "confluence-url-routing")
      var instId = meta.id || path.basename(files[fi], ".md");

      // Threshold matching: require min_matches keyword hits (default 2).
      // Rules can set min_matches: 1 in frontmatter for unique/URL keywords.
      var minMatches = parseInt(meta.min_matches, 10) || 2;
      var hits = [];
      for (var ki = 0; ki < meta.keywords.length; ki++) {
        var kw = meta.keywords[ki].toLowerCase().trim();
        if (kw && promptLower.indexOf(kw) !== -1) { hits.push(kw); }
      }
      if (hits.length < minMatches) continue;
      lastMatchedRules.push({ id: instId, reason: hits.join("+"), action: meta.action || null });

      if (cache.loaded.indexOf(instId) !== -1) {
        instLog("[KEYWORD] trigger=\"" + (prompt || "").slice(0, 40) + "\" match=" + hits.join("+") + " (" + hits.length + "/" + minMatches + ") -> " + files[fi] + " (cached)");
        continue;
      }

      cache.loaded.push(instId);
      instLog("[KEYWORD] trigger=\"" + (prompt || "").slice(0, 40) + "\" match=" + hits.join("+") + " (" + hits.length + "/" + minMatches + ") -> " + files[fi] + " (loaded)");
      outputs.push("--- RULE: " + instId + " ---");
      outputs.push(meta.body);
      outputs.push("--- END RULE ---");
    }

    fs.writeFileSync(CACHE_FILE, JSON.stringify(cache));
    if (outputs.length > 0) return outputs.join(String.fromCharCode(10));
  } catch (e) {
    log("ruleLoader", "ERROR", e.message);
  }
  return null;
}

// ===== MODULE: configCheck =====
function moduleConfigCheck() {
  const crypto = require("crypto");
  const HASH_FILE = path.join(HOME, ".claude", "hooks", ".config-hash");
  const SF = path.join(HOME, ".claude", "settings.json");
  const RF = path.join(HOME, ".claude", "hooks", "skill-registry.json");
  try {
    var lastHash = fs.existsSync(HASH_FILE) ? fs.readFileSync(HASH_FILE, "utf-8").trim() : null;
    if (!lastHash) { log("configCheck", "DEBUG", "no baseline hash yet"); return null; }
    var sRaw = fs.existsSync(SF) ? fs.readFileSync(SF, "utf-8") : "{}";
    var rRaw = fs.existsSync(RF) ? fs.readFileSync(RF, "utf-8") : "{}";
    var settings = JSON.parse(sRaw);
    var registry = JSON.parse(rRaw);
    var hooks = [];
    for (var [event, entries] of Object.entries(settings.hooks || {})) {
      for (var entry of entries) {
        for (var h of (entry.hooks || [])) {
          var cmdParts = (h.command || "").split('"');
          var fname = "unknown";
          for (var p of cmdParts) { if (p.trim().endsWith(".js") || p.trim().endsWith(".sh")) { fname = path.basename(p.trim()).replace(/[.](js|sh)$/, ""); break; } }
          hooks.push({ event: event, matcher: entry.matcher || "*", name: fname, async: h.async || false });
        }
      }
    }
    var skills = [];
      var regIds = new Set();
      for (var rs of (registry.skills || [])) { skills.push({ id: rs.id, name: rs.name, enabled: rs.enabled || false, managed: true }); regIds.add(rs.id); }
      var SKILLS_DIR = path.join(HOME, ".claude", "skills");
      try {
        var allDirs = fs.readdirSync(SKILLS_DIR).filter(function(d) { try { return fs.statSync(path.join(SKILLS_DIR, d)).isDirectory(); } catch { return false; } });
        for (var dir of allDirs) { if (!regIds.has(dir)) skills.push({ id: dir, name: dir, enabled: false, managed: false }); }
      } catch {}
    // Parse MCP servers for hash alignment with config-awareness
    var MCP_PATHS = [
      path.join(HOME, "OneDrive - TrendMicro", "Documents", "ProjectsCL", "MCP", "mcp-manager", "servers.yaml"),
      path.join(HOME, "mcp", "mcp-manager", "servers.yaml")
    ];
    var yamlPath = MCP_PATHS.find(function(p) { return fs.existsSync(p); });
    var servers = [];
    if (yamlPath) {
      var yaml = fs.readFileSync(yamlPath, "utf-8");
      var cur = null;
      for (var ln of yaml.split(String.fromCharCode(10))) {
        var t = ln.trim();
        var ind = ln.length - ln.trimStart().length;
        if (ind === 2 && t.endsWith(":") && !t.includes(" ")) {
          cur = t.slice(0, -1);
          servers.push({ name: cur, enabled: false, managed: true, description: "" });
        }
        if (cur && t.startsWith("enabled:")) servers[servers.length - 1].enabled = t.includes("true");
        if (cur && t.startsWith("description:")) servers[servers.length - 1].description = t.split(":").slice(1).join(":").trim();
      }
    }
    // Scan rules directory
    var INST_DIR = path.join(HOME, ".claude", "rules");
    var instFiles = [];
    try {
      instFiles = fs.readdirSync(INST_DIR).filter(function(f) { return f.endsWith(".md") && f !== "README.md"; }).map(function(f) {
        var content = fs.readFileSync(path.join(INST_DIR, f), "utf-8");
        if (!content.startsWith("---")) return null;
        var end = content.indexOf("---", 3);
        if (end === -1) return null;
        var yaml = content.substring(3, end).trim();
        var id = "unknown";
        for (var line of yaml.split(String.fromCharCode(10))) { if (line.trim().startsWith("id:")) { id = line.split(":").slice(1).join(":").trim(); break; } }
        return { id: id };
      }).filter(Boolean);
    } catch {}

    // Normalize to minimal fields (must match config-awareness.js computeHash)
    var hNorm = hooks.map(function(x) { return { event: x.event, matcher: x.matcher, name: x.name, async: x.async }; });
    var mNorm = servers.map(function(x) { return { name: x.name, enabled: x.enabled }; });
    var sNorm = skills.map(function(x) { return { id: x.id, enabled: x.enabled }; });
    var iNorm = instFiles;
    var curHash = crypto.createHash("md5").update(JSON.stringify({ hooks: hNorm, servers: mNorm, skills: sNorm, rules: iNorm })).digest("hex");
    if (curHash === lastHash) return null;
    fs.writeFileSync(HASH_FILE, curHash);
    log("configCheck", "INFO", "config changed: " + lastHash.slice(0,8) + " -> " + curHash.slice(0,8));
    // Append to config report
    var REPORT = path.join(HOME, ".claude", "config-report.md");
    try {
      var rpt = fs.existsSync(REPORT) ? fs.readFileSync(REPORT, "utf-8") : "";
      var now = new Date().toISOString().replace("T", " ").slice(0, 19);
      var entry = "- " + now + " - Config changed mid-session (hash=" + lastHash.slice(0,8) + " -> " + curHash.slice(0,8) + ")";
      var clMarker = "## Change Log";
      var clIdx = rpt.indexOf(clMarker);
      if (clIdx !== -1) {
        var before = rpt.substring(0, clIdx + clMarker.length);
        var after = rpt.substring(clIdx + clMarker.length);
        var NL = String.fromCharCode(10);
        rpt = before + NL + NL + entry + after;
        fs.writeFileSync(REPORT, rpt);
      }
    } catch (re) {}
    var out = ["--- CONFIG CHANGE DETECTED ---", "Claude config modified. Current state:", ""];
    var byEv = {};
    for (var hk of hooks) { if (!byEv[hk.event]) byEv[hk.event] = []; byEv[hk.event].push(hk); }
    for (var [ev, evH] of Object.entries(byEv)) out.push("  " + ev + ": " + evH.map(function(x){return x.name;}).join(", "));
    out.push("");
    out.push("Active skills: " + (skills.length > 0 ? skills.map(function(s){return s.id;}).join(", ") : "none"));
    out.push("--- END CONFIG CHANGE ---");
    return out.join("\n");
  } catch (e) { log("configCheck", "ERROR", e.message); }
  return null;
}

// ===== MODULE: writePendingSuggestions =====
function writePendingSuggestions(skills, mcps, rules, prompt) {
  try {
    // Only write if there are skill or MCP suggestions (rules are context-only)
    if (skills.length === 0 && mcps.length === 0) {
      // Clean up stale state file if no suggestions
      if (fs.existsSync(STATE_FILE)) {
        try { fs.unlinkSync(STATE_FILE); } catch {}
      }
      return;
    }
    if (!fs.existsSync(STATE_DIR)) fs.mkdirSync(STATE_DIR, { recursive: true });
    const state = {
      timestamp: new Date().toISOString(),
      prompt_snippet: (prompt || String()).slice(0, 80),
      suggestions: {
        skills: skills,
        mcps: mcps,
        rules: rules
      },
      fulfilled: []
    };
    fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
    log("enforcement", "INFO", "wrote pending suggestions: " + skills.length + " skills, " + mcps.length + " mcps, " + rules.length + " rules");
  } catch (e) {
    log("enforcement", "ERROR", "writePendingSuggestions failed: " + e.message);
  }
}

// ===== MODULE: observability =====
function writeObservability(skills, mcps, rules) {
  var summaryParts = [];
  if (skills.length > 0) {
    summaryParts.push("[SM] Loaded " + skills.length + " skill(s): " + skills.map(function(s) { return s.id + ' (kw: "' + s.reason + '")'; }).join(", "));
  }
  if (mcps.length > 0) {
    summaryParts.push("[SM] Loaded " + mcps.length + " MCP(s): " + mcps.map(function(m) { return m.name + ' (kw: "' + m.reason + '")'; }).join(", "));
  }
  if (rules.length > 0) {
    summaryParts.push("[SM] Loaded " + rules.length + " rule(s):");
    for (var ii = 0; ii < rules.length; ii++) {
      var inst = rules[ii];
      var line = '  [RULE] ' + inst.id + ' (kw: "' + inst.reason + '")';
      if (inst.action) {
        line += '\n    ACTION: ' + inst.action;
      }
      summaryParts.push(line);
    }
  }

  // Write status-line-cache
  try {
    var cacheDir = path.dirname(STATUS_CACHE);
    if (!fs.existsSync(cacheDir)) fs.mkdirSync(cacheDir, { recursive: true });
    var cacheData = {
      timestamp: new Date().toISOString(),
      event: "UserPromptSubmit",
      loaded: {
        skills: skills.map(function(s) { return s.id; }),
        mcps: mcps.map(function(m) { return m.name; }),
        rules: rules.map(function(i) { return i.id; })
      },
      total: skills.length + mcps.length + rules.length
    };
    fs.writeFileSync(STATUS_CACHE, JSON.stringify(cacheData, null, 2));
  } catch (e) {
    log("observability", "ERROR", "status-line-cache write failed: " + e.message);
  }

  // Log summary
  if (summaryParts.length > 0) {
    log("observability", "INFO", summaryParts.join(" | "));
  }

  // Return summary for TUI injection (prepended to outputs)
  if (summaryParts.length > 0) {
    return "--- SUPER-MANAGER LOADED ---\n" + summaryParts.join("\n") + "\n--- END LOADED ---";
  }
  return null;
}

// ===== GUARD: background notification detection =====
function isBackgroundNotification(prompt) {
  if (!prompt || prompt.length < 2) return true;
  // Task completion notifications from background agents
  if (prompt.indexOf('(type: local_agent)') !== -1) return true;
  if (prompt.indexOf('(status: completed)') !== -1) return true;
  if (prompt.indexOf('(status: running)') !== -1) return true;
  // System-reminder injection artifacts
  if (prompt.indexOf('task_id') !== -1 && prompt.indexOf('status') !== -1 && prompt.length < 200) return true;
  return false;
}

// ===== MAIN =====
async function main() {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;

  let hookData;
  try { hookData = JSON.parse(input); } catch (e) { process.exit(0); }

  const prompt = (hookData.prompt || '').toLowerCase();
  if (!prompt) process.exit(0);

  // Skip processing for background task notifications
  if (isBackgroundNotification(prompt)) {
    log('main', 'DEBUG', 'skipped - background notification detected');
    process.exit(0);
  }

  const outputs = [];

  // Run all modules
  const claudemd = moduleClaudeMd();
  if (claudemd) outputs.push(claudemd);

  const skill = moduleSkill(prompt);
  if (skill) outputs.push(skill);

  const mcp = moduleMcp(prompt);

  const ruleLoader = moduleRuleLoader(prompt);
  if (ruleLoader) outputs.push(ruleLoader);

  const configDelta = moduleConfigCheck();
  if (configDelta) outputs.push(configDelta);
  if (mcp) outputs.push(mcp);

  // Write pending suggestions for enforcement hooks
  writePendingSuggestions(lastMatchedSkills, lastMatchedMcps, lastMatchedRules, prompt);

  // Observability: TUI + log + status-line-cache
  var obsSummary = writeObservability(lastMatchedSkills, lastMatchedMcps, lastMatchedRules);
  if (obsSummary) outputs.unshift(obsSummary);

  if (outputs.length > 0) {
    console.log(outputs.join('\n'));
  }

  process.exit(0);
}

main().catch(() => process.exit(0));
