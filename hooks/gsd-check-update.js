#!/usr/bin/env node
/**
 * @hook gsd-check-update
 * @event SessionStart
 * @matcher *
 * @description Checks for GSD (Get Shit Done) framework updates in the background.
 *   Spawns a detached process that queries npm for the latest get-shit-done-cc
 *   version and compares against the installed version. Results are cached to
 *   ~/.claude/cache/gsd-update-check.json. If an update is available, the
 *   gsd-statusline hook will display an upgrade prompt.
 */
const log = require('./hook-logger');
const HOOK_NAME = 'gsd-check-update';
const EVENT_TYPE = 'SessionStart';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn } = require('child_process');

const homeDir = os.homedir();
const cwd = process.cwd();
const cacheDir = path.join(homeDir, '.claude', 'cache');
const cacheFile = path.join(cacheDir, 'gsd-update-check.json');
const projectVersionFile = path.join(cwd, '.claude', 'get-shit-done', 'VERSION');
const globalVersionFile = path.join(homeDir, '.claude', 'get-shit-done', 'VERSION');

if (!fs.existsSync(cacheDir)) {
  fs.mkdirSync(cacheDir, { recursive: true });
}

log(HOOK_NAME, EVENT_TYPE, 'spawning background update check');

const child = spawn(process.execPath, ['-e', `
  const fs = require('fs');
  const { execSync } = require('child_process');
  const cacheFile = ${JSON.stringify(cacheFile)};
  const projectVersionFile = ${JSON.stringify(projectVersionFile)};
  const globalVersionFile = ${JSON.stringify(globalVersionFile)};

  let installed = '0.0.0';
  try {
    if (fs.existsSync(projectVersionFile)) {
      installed = fs.readFileSync(projectVersionFile, 'utf8').trim();
    } else if (fs.existsSync(globalVersionFile)) {
      installed = fs.readFileSync(globalVersionFile, 'utf8').trim();
    }
  } catch (e) {}

  let latest = null;
  try {
    latest = execSync('npm view get-shit-done-cc version', { encoding: 'utf8', timeout: 10000, windowsHide: true }).trim();
  } catch (e) {}

  const result = {
    update_available: latest && installed !== latest,
    installed,
    latest: latest || 'unknown',
    checked: Math.floor(Date.now() / 1000)
  };
  fs.writeFileSync(cacheFile, JSON.stringify(result));
`], { stdio: 'ignore', windowsHide: true });

child.unref();
