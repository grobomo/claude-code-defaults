#!/usr/bin/env node
/**
 * Claude Code Settings Validator
 * Run this before starting Claude to catch hook configuration errors
 *
 * Usage: node ~/.claude/hooks/validate-settings.js
 */

const fs = require('fs');
const path = require('path');

// Handle both Windows and WSL paths
let HOME = process.env.HOME || process.env.USERPROFILE;

// If running in WSL, use Windows home directory
if (process.platform === 'linux' && HOME.startsWith('/home/')) {
  // Get Windows username from WSL environment
  const username = process.env.LOGNAME ||
                   process.env.USER ||
                   require('os').userInfo().username;

  // Try to detect Windows username from current path
  const wslMatch = process.cwd().match(/^\/mnt\/c\/Users\/([^\/]+)/);
  if (wslMatch) {
    HOME = `/mnt/c/Users/${wslMatch[1]}`;
  } else {
    HOME = `/mnt/c/Users/${username}`;
  }
}

const SETTINGS_PATH = path.join(HOME, '.claude', 'settings.json');

function validateSettings() {
  console.log('🔍 Validating Claude Code settings...\n');
  console.log(`Looking for: ${SETTINGS_PATH}\n`);

  // Check if settings file exists
  if (!fs.existsSync(SETTINGS_PATH)) {
    console.log('✅ No settings file found - Claude will use defaults');
    return true;
  }

  let settings;
  try {
    const content = fs.readFileSync(SETTINGS_PATH, 'utf8');
    settings = JSON.parse(content);
  } catch (err) {
    console.error('❌ FATAL: Invalid JSON in settings.json');
    console.error(`   ${err.message}`);
    console.error(`\n   Fix: Check ${SETTINGS_PATH} for syntax errors`);
    return false;
  }

  let errors = 0;
  let warnings = 0;

  // Validate hooks structure
  if (settings.hooks) {
    const hookTypes = ['SessionStart', 'UserPromptSubmit', 'PostToolUse', 'Stop'];

    for (const hookType of hookTypes) {
      if (!settings.hooks[hookType]) continue;

      const hooks = settings.hooks[hookType];

      // Check for nested arrays (common mistake)
      if (Array.isArray(hooks)) {
        for (let i = 0; i < hooks.length; i++) {
          const hook = hooks[i];

          if (hook.hooks) {
            console.error(`❌ ERROR: ${hookType}[${i}] has nested "hooks" array`);
            console.error(`   This will break Claude Code startup!`);
            console.error(`   Fix: Remove the nested "hooks" wrapper\n`);
            errors++;
          }

          // Validate hook has required fields
          if (!hook.type) {
            console.error(`❌ ERROR: ${hookType}[${i}] missing "type" field`);
            errors++;
          }

          if (hook.type === 'command' && !hook.command) {
            console.error(`❌ ERROR: ${hookType}[${i}] missing "command" field`);
            errors++;
          }
        }
      } else {
        console.error(`❌ ERROR: ${hookType} must be an array`);
        errors++;
      }
    }
  }

  // Validate statusLine
  if (settings.statusLine) {
    if (!settings.statusLine.type) {
      console.error('❌ ERROR: statusLine missing "type" field');
      errors++;
    }
    if (settings.statusLine.type === 'command' && !settings.statusLine.command) {
      console.error('❌ ERROR: statusLine missing "command" field');
      errors++;
    }
  }

  // Report results
  console.log('─'.repeat(60));
  if (errors === 0 && warnings === 0) {
    console.log('✅ Settings are valid! Safe to start Claude Code.\n');
    return true;
  } else {
    console.log(`\n❌ Found ${errors} error(s), ${warnings} warning(s)`);
    console.log(`\n⚠️  DO NOT start Claude Code until errors are fixed!`);
    console.log(`   Starting with invalid settings will break Claude Code.\n`);
    return false;
  }
}

// Run validation
const isValid = validateSettings();
process.exit(isValid ? 0 : 1);
