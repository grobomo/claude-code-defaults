/**
 * Central hook logger
 * Usage: require('./hook-logger')('hook-name', 'EventType', 'message')
 */
const fs = require('fs');
const path = require('path');

const LOG_FILE = path.join(process.env.HOME || process.env.USERPROFILE, '.claude', 'hooks', 'hooks.log');

module.exports = function log(hookName, eventType, message, level = 'INFO') {
  const timestamp = new Date().toISOString();
  const line = `${timestamp} [${level}] [${eventType}] [${hookName}] ${message}\n`;
  try {
    fs.appendFileSync(LOG_FILE, line);
  } catch (e) {}
};
