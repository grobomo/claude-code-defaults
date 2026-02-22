#!/usr/bin/env node
/**
 * @hook instruction-stop
 * @event Stop
 * @description Checks Claude's last response against Stop instructions.
 *   Supports two matching modes in frontmatter:
 *     - pattern: regex string - combinatorial regex match
 *     - keywords: [array] - exact substring matches
 *   If matched, blocks Claude from stopping and injects correction instructions.
 *
 * Stop hook contract (from hook-manager SKILL.md):
 *   stdin:  {session_id, stop_hook_active, last_assistant_message, transcript_path}
 *   stdout: {"decision":"block","reason":"..."} to block, or nothing to allow
 */
var fs = require("fs");
var path = require("path");
var os = require("os");

var HOME = os.homedir();
var INST_DIR = path.join(HOME, ".claude", "instructions", "Stop");
var LOG_FILE = path.join(HOME, ".claude", "instructions", "stop-loader.log");

function log(msg) {
  var ts = new Date().toISOString().replace("T", " ").slice(0, 19);
  try {
    fs.appendFileSync(LOG_FILE, ts + " " + msg + "\n");
  } catch (e) {}
}

function parseFrontmatter(content) {
  if (!content.startsWith("---")) return null;
  var endIdx = content.indexOf("---", 3);
  if (endIdx === -1) return null;
  var yaml = content.substring(3, endIdx).trim();
  var meta = {};
  var lines = yaml.split("\n");
  for (var i = 0; i < lines.length; i++) {
    var col = lines[i].indexOf(":");
    if (col === -1) continue;
    var key = lines[i].substring(0, col).trim();
    var val = lines[i].substring(col + 1).trim();
    if (val.startsWith("[") && val.endsWith("]")) {
      meta[key] = val.slice(1, -1).split(",").map(function (s) { return s.trim(); });
    } else {
      meta[key] = val;
    }
  }
  meta.body = content.substring(endIdx + 3).trim();
  return meta;
}

// Read stdin SYNCHRONOUSLY via file descriptor 0 (cross-platform)
var input = "";
try {
  input = fs.readFileSync(0, "utf-8");
} catch (e) {
  log("[STOP] ERROR reading stdin: " + e.message);
  process.exit(0);
}

if (!input) process.exit(0);

var hookData;
try {
  hookData = JSON.parse(input);
} catch (e) {
  log("[STOP] ERROR: bad JSON on stdin");
  process.exit(0);
}

var responseText = hookData.last_assistant_message || "";
if (!responseText) {
  log("[STOP] no last_assistant_message, allowing stop");
  process.exit(0);
}

var responseLower = responseText.toLowerCase();
var safePreview = responseText.substring(0, 120).split("\n").join("\n");
log("[STOP] response length=" + responseText.length + " first120=" + safePreview);

// Load instruction files from Stop/ directory
var files;
try {
  files = fs.readdirSync(INST_DIR).filter(function (f) { return f.endsWith(".md"); });
} catch (e) {
  process.exit(0);
}

if (files.length === 0) process.exit(0);

var matched = [];

for (var i = 0; i < files.length; i++) {
  var filePath = path.join(INST_DIR, files[i]);
  var content;
  try {
    content = fs.readFileSync(filePath, "utf-8");
  } catch (e) {
    continue;
  }

  var meta = parseFrontmatter(content);
  if (!meta || !meta.id) continue;

  var hit = false;

  // Check regex pattern first (single string - supports commas in quantifiers)
  if (meta.pattern && typeof meta.pattern === "string" && meta.pattern.length > 0) {
    try {
      var re = new RegExp(meta.pattern, "i");
      if (re.test(responseText)) {
        log("[STOP] pattern hit -> " + files[i]);
        hit = true;
      }
    } catch (e) {
      log("[STOP] bad regex: " + e.message);
    }
  }

  // Then check substring keywords
  if (!hit && meta.keywords && Array.isArray(meta.keywords)) {
    for (var k = 0; k < meta.keywords.length; k++) {
      var kw = meta.keywords[k].toLowerCase();
      if (kw && responseLower.indexOf(kw) !== -1) {
        log("[STOP] keyword=\"" + meta.keywords[k] + "\" -> " + files[i]);
        hit = true;
        break;
      }
    }
  }

  if (hit) {
    matched.push(meta.body);
  }
}

if (matched.length === 0) {
  log("[STOP] no match, allowing stop");
  process.exit(0);
}

log("[STOP] BLOCKING - " + matched.length + " instruction(s) matched");
process.stdout.write(JSON.stringify({
  decision: "block",
  reason: matched.join("\n\n")
}));
process.exit(0);
