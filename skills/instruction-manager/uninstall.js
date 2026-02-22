#!/usr/bin/env node
/**
 * Instruction Manager Uninstall
 *
 * Restores from the most recent backup created by setup.js.
 * Archives (never deletes) any files that setup created.
 *
 * Usage:
 *   node uninstall.js
 */

var fs = require('fs');
var path = require('path');
var os = require('os');

var HOME = os.homedir();
var CLAUDE_DIR = path.join(HOME, '.claude');
var UTILS_PATH = path.join(CLAUDE_DIR, 'super-manager', 'shared', 'setup-utils.js');

// Load shared utilities
var utils;
try {
  utils = require(UTILS_PATH);
} catch (e) {
  console.log('[instruction-manager:uninstall] ERROR: Cannot load setup-utils.js');
  console.log('[instruction-manager:uninstall] Expected at: ' + UTILS_PATH);
  console.log('[instruction-manager:uninstall] ' + e.message);
  process.exit(1);
}

var MANAGER_NAME = 'instruction-manager';

// ================================================================
// Main
// ================================================================

function main() {
  console.log('');
  console.log('[instruction-manager:uninstall] ============================================');
  console.log('[instruction-manager:uninstall] Instruction Manager Uninstall');
  console.log('[instruction-manager:uninstall] ============================================');
  console.log('');

  // -- Find latest backup --
  var backupDir = utils.findLatestBackup(MANAGER_NAME);
  if (!backupDir) {
    console.log('[instruction-manager:uninstall] ERROR: No backups found for ' + MANAGER_NAME);
    console.log('[instruction-manager:uninstall] Nothing to restore. Aborting.');
    process.exit(1);
  }

  var manifestPath = path.join(backupDir, 'manifest.json');
  if (!fs.existsSync(manifestPath)) {
    console.log('[instruction-manager:uninstall] ERROR: No manifest.json in ' + backupDir);
    process.exit(1);
  }

  var manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  console.log('[instruction-manager:uninstall] Backup found: ' + backupDir);
  console.log('[instruction-manager:uninstall] Timestamp: ' + manifest.timestamp);
  console.log('[instruction-manager:uninstall] Files backed up: ' + manifest.files.length);
  console.log('[instruction-manager:uninstall] Files created by setup: ' + (manifest.created ? manifest.created.length : 0));
  console.log('');

  // -- Restore from backup --
  console.log('[instruction-manager:uninstall] Restoring...');
  var result = utils.restore(backupDir);

  // Report restored files
  if (result.restored.length > 0) {
    console.log('[instruction-manager:uninstall] Restored:');
    for (var i = 0; i < result.restored.length; i++) {
      console.log('[instruction-manager:uninstall]   ' + path.relative(CLAUDE_DIR, result.restored[i]));
    }
  }

  // Report archived (removed) files
  if (result.removed.length > 0) {
    console.log('[instruction-manager:uninstall] Archived (created by setup):');
    for (var j = 0; j < result.removed.length; j++) {
      console.log('[instruction-manager:uninstall]   ' + path.relative(CLAUDE_DIR, result.removed[j]));
    }
  }

  // Report errors
  if (result.errors.length > 0) {
    console.log('[instruction-manager:uninstall] Errors:');
    for (var k = 0; k < result.errors.length; k++) {
      console.log('[instruction-manager:uninstall]   [!] ' + result.errors[k]);
    }
  }

  // -- Remove from skill-registry.json if present --
  var registryPath = path.join(CLAUDE_DIR, 'hooks', 'skill-registry.json');
  if (fs.existsSync(registryPath)) {
    try {
      var registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
      if (registry.skills && Array.isArray(registry.skills)) {
        var before = registry.skills.length;
        registry.skills = registry.skills.filter(function (s) {
          return s.id !== MANAGER_NAME;
        });
        if (registry.skills.length < before) {
          fs.writeFileSync(registryPath, JSON.stringify(registry, null, 2), 'utf8');
          console.log('[instruction-manager:uninstall] Removed from skill-registry.json');
        }
      }
    } catch (e) {
      console.log('[instruction-manager:uninstall] Warning: Could not update skill-registry.json: ' + e.message);
    }
  }

  // -- Summary --
  console.log('');
  console.log('[instruction-manager:uninstall] ============================================');
  console.log('[instruction-manager:uninstall] Uninstall Complete');
  console.log('[instruction-manager:uninstall] ============================================');
  console.log('[instruction-manager:uninstall] Restored: ' + result.restored.length + ' file(s)');
  console.log('[instruction-manager:uninstall] Archived: ' + result.removed.length + ' file(s)');
  console.log('[instruction-manager:uninstall] Errors: ' + result.errors.length);
  console.log('[instruction-manager:uninstall]');
  console.log('[instruction-manager:uninstall] SKILL.md preserved - skill is still available.');
  console.log('[instruction-manager:uninstall] Re-install: node ~/.claude/skills/instruction-manager/setup.js');
  console.log('[instruction-manager:uninstall] ============================================');
  console.log('');
}

// ================================================================
// Exports
// ================================================================

module.exports = { main: main };

if (require.main === module) main();
