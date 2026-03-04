/**
 * @hook session-end-report
 * @event SessionEnd
 * @async true
 *
 * Generates HTML effectiveness report at session end and opens in browser.
 * Runs the super-manager analyzer to produce a dashboard showing:
 *   - Rule loader triggers
 *   - Skill/MCP matcher stats
 *   - Enforcement gate events
 *   - Stop hook fires
 *   - Recommendations
 */
var path = require("path");
var fs = require("fs");
var child_process = require("child_process");

var HOME = process.env.HOME || process.env.USERPROFILE || "";
var PYTHON = process.env.PYTHON || "python";
var SM_DIR = path.join(HOME, ".claude", "super-manager");
var REPORT = path.join(SM_DIR, "reports", "effectiveness-dashboard.html");
var LOG_FILE = path.join(HOME, ".claude", "hooks", "hooks.log");

function log(msg) {
  var ts = new Date().toISOString();
  try {
    fs.appendFileSync(LOG_FILE, ts + " [INFO] [SessionEnd] [session-end-report] " + msg + "\n");
  } catch (e) {}
}

try {
  // Run analyzer with --html flag
  var cmd = PYTHON + ' "' + path.join(SM_DIR, "super_manager.py") + '" analyze --html';
  log("running: " + cmd);

  var result = child_process.execSync(cmd, {
    cwd: SM_DIR,
    timeout: 60000,
    encoding: "utf-8",
    stdio: ["pipe", "pipe", "pipe"],
  });

  log("analyzer completed: " + (result || "").trim().split("\n")[0]);

  // Open HTML report in browser
  if (fs.existsSync(REPORT)) {
    var platform = process.platform;
    if (platform === "win32") {
      child_process.execSync('start "" "' + REPORT + '"', { shell: true });
    } else if (platform === "darwin") {
      child_process.execSync('open "' + REPORT + '"');
    } else {
      child_process.execSync('xdg-open "' + REPORT + '" 2>/dev/null || true', { shell: true });
    }
    log("opened report in browser");
  } else {
    log("report not found at " + REPORT);
  }
} catch (e) {
  log("error: " + (e.message || String(e)).slice(0, 200));
}
