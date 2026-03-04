#!/usr/bin/env node
/**
 * @hook skill-manager-session
 * @event SessionStart
 * @matcher *
 * @description Hook health check + auto-enrich on session start
 */
const fs = require("fs");
const path = require("path");
const os = require("os");

const HOME = os.homedir();
const HOOKS_DIR = path.join(HOME, ".claude", "hooks");
const SKILLS_DIR = path.join(HOME, ".claude", "skills");
const SETTINGS_PATH = path.join(HOME, ".claude", "settings.json");
const LOG_FILE = path.join(HOME, ".claude", "logs", "skill-usage.log");

function log(action, detail) {
  try {
    var dir = path.dirname(LOG_FILE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    var e = { timestamp: new Date().toISOString(), tool: "SessionStart", skill: "skill-manager", action: action, detail: detail };
    fs.appendFileSync(LOG_FILE, JSON.stringify(e) + "\n");
  } catch {}
}

function main() {
  try {
    var issues = [];
    var fixed = [];

    // 1. Check required hook files exist
    var required = ["skill-usage-tracker.js", "skill-manager-session.js"];
    for (var r of required) {
      if (!fs.existsSync(path.join(HOOKS_DIR, r))) issues.push("missing:" + r);
    }

    // 2. Check settings.json has hooks registered
    try {
      var sStr = fs.readFileSync(SETTINGS_PATH, "utf-8");
      for (var r of required) {
        if (sStr.indexOf(r) === -1) issues.push("unregistered:" + r);
      }
    } catch {}

    // 3. Auto-remediate missing hooks
    if (issues.length > 0) {
      log("health_issues", issues.join(", "));
      var setupPath = path.join(SKILLS_DIR, "skill-manager", "setup.js");
      if (fs.existsSync(setupPath)) {
        try {
          delete require.cache[require.resolve(setupPath)];
          var setup = require(setupPath);
          if (typeof setup.installHooks === "function") {
            var hr = setup.installHooks();
            if (hr.installed.length > 0) fixed.push("installed:" + hr.installed.join(","));
          }
          if (typeof setup.patchSettings === "function") {
            var sr = setup.patchSettings();
            if (sr.added.length > 0) fixed.push("registered:" + sr.added.join(","));
          }
        } catch {}
      }
      if (fixed.length > 0) log("health_fixed", fixed.join("; "));
      else log("health_unfixed", "setup.js not found or failed");
    } else {
      log("health_ok", required.length + " hooks verified");
    }

    // 4. Check frontmatter compliance
    if (fs.existsSync(SKILLS_DIR)) {
      var entries = fs.readdirSync(SKILLS_DIR);
      var missing = [];
      for (var entry of entries) {
        var dirPath = path.join(SKILLS_DIR, entry);
        try { if (!fs.statSync(dirPath).isDirectory()) continue; } catch { continue; }
        if (entry === "archive" || entry.endsWith(".zip")) continue;
        var skillMd = path.join(dirPath, "SKILL.md");
        if (!fs.existsSync(skillMd)) continue;
        var content = fs.readFileSync(skillMd, "utf-8");
        var hasKw = false;
        if (content.startsWith("---")) {
          var endIdx = content.indexOf("---", 3);
          if (endIdx !== -1) {
            var fm = content.substring(3, endIdx);
            hasKw = fm.indexOf("keywords:") !== -1;
          }
        }
        if (!hasKw) missing.push(entry);
      }
      if (missing.length > 0) {
        log("frontmatter_missing", missing.join(", "));
        var setupPath2 = path.join(SKILLS_DIR, "skill-manager", "setup.js");
        if (fs.existsSync(setupPath2)) {
          try {
            delete require.cache[require.resolve(setupPath2)];
            var setup2 = require(setupPath2);
            var inv = setup2.scanAllSkills();
            setup2.enrichAllSkills(inv);
            if (typeof setup2.buildSkillRegistry === "function") setup2.buildSkillRegistry(inv, []);
            log("frontmatter_enriched", inv.length + " skills processed");
          } catch {}
        }
      }
    }

    console.log("{}");
  } catch {
    console.log("{}");
  }
}

main();