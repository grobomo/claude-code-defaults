#!/usr/bin/env node
/**
 * @hook skill-usage-tracker
 * @event PostToolUse
 * @matcher Skill|Task
 * @description Log Skill/Task usage for analytics
 */
const fs = require("fs");
const path = require("path");
const os = require("os");

const HOME = os.homedir();
const LOG_FILE = path.join(HOME, ".claude", "logs", "skill-usage.log");

async function main() {
  try {
    let input = "";
    for await (const chunk of process.stdin) input += chunk;
    let data;
    try { data = JSON.parse(input); } catch { console.log("{}"); return; }

    var toolName = data.tool_name || "";
    var toolInput = data.tool_input || {};
    var skillName = null;
    if (toolName === "Skill") skillName = toolInput.skill || null;
    else if (toolName === "Task") skillName = toolInput.name || toolInput.subagent_type || null;
    if (!skillName) { console.log("{}"); return; }

    var logDir = path.dirname(LOG_FILE);
    if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
    var entry = {
      timestamp: new Date().toISOString(),
      tool: toolName,
      skill: skillName
    };
    fs.appendFileSync(LOG_FILE, JSON.stringify(entry) + "\n");
    console.log("{}");
  } catch {
    console.log("{}");
  }
}

main().catch(function() { console.log("{}"); process.exit(0); });