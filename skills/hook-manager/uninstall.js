#!/usr/bin/env node
/**
 * @module hook-manager/uninstall
 * Hook Manager Uninstall - restores from backup, archives created files.
 *
 * WHY: Every sub-manager must have a one-click uninstall that returns the
 * user to exactly the state they were in before setup ran. This script
 * reads the backup manifest to know what to restore and what to archive.
 *
 * Usage:
 *   node uninstall.js        # Restore from latest backup
 */
var fs = require('fs');
var path = require('path');
var os = require('os');

var HOME = os.homedir();
var CLAUDE_DIR = path.join(HOME, '.claude');
var MANAGER_NAME = 'hook-manager';

// -------------------------------------------------------------------------
// Load shared setup-utils (fallback to inline if not found)
// -------------------------------------------------------------------------

var utils = null;
var UTILS_PATH = path.join(CLAUDE_DIR, 'super-manager', 'shared', 'setup-utils.js');
if (fs.existsSync(UTILS_PATH)) {
  utils = require(UTILS_PATH);
}

// -------------------------------------------------------------------------
// Find latest backup
// -------------------------------------------------------------------------

/**
 * Find the most recent backup directory for hook-manager.
 * @returns {string|null}
 */
function findLatestBackup() {
  if (utils) {
    return utils.findLatestBackup(MANAGER_NAME);
  }

  // Inline fallback
  var managerBackups = path.join(CLAUDE_DIR, 'backups', MANAGER_NAME);
  if (!fs.existsSync(managerBackups)) return null;
  var dirs = fs.readdirSync(managerBackups).sort().reverse();
  return dirs.length > 0 ? path.join(managerBackups, dirs[0]) : null;
}

// -------------------------------------------------------------------------
// Restore from backup
// -------------------------------------------------------------------------

/**
 * Restore files from backup manifest and archive created files.
 * @param {string} backupDir
 * @returns {{ restored: string[], removed: string[], errors: string[] }}
 */
function restoreFromBackup(backupDir) {
  if (utils) {
    return utils.restore(backupDir);
  }

  // Inline fallback
  var result = { restored: [], removed: [], errors: [] };
  var manifestPath = path.join(backupDir, 'manifest.json');

  if (!fs.existsSync(manifestPath)) {
    result.errors.push('No manifest.json in ' + backupDir);
    return result;
  }

  var manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));

  // Restore backed-up files to their original locations
  for (var i = 0; i < manifest.files.length; i++) {
    var entry = manifest.files[i];
    var src = path.join(backupDir, entry.backed);
    if (!fs.existsSync(src)) {
      result.errors.push('Backup file missing: ' + entry.backed);
      continue;
    }
    try {
      fs.mkdirSync(path.dirname(entry.original), { recursive: true });
      fs.copyFileSync(src, entry.original);
      result.restored.push(entry.original);
    } catch (e) {
      result.errors.push('Failed to restore ' + entry.original + ': ' + e.message);
    }
  }

  // Archive files that were created by setup (not pre-existing)
  if (manifest.created && manifest.created.length > 0) {
    for (var j = 0; j < manifest.created.length; j++) {
      var f = manifest.created[j];
      if (fs.existsSync(f)) {
        var archiveDir = path.join(CLAUDE_DIR, 'archive', MANAGER_NAME);
        fs.mkdirSync(archiveDir, { recursive: true });
        var ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        var archiveName = path.basename(f) + '.' + ts;
        fs.renameSync(f, path.join(archiveDir, archiveName));
        result.removed.push(f);
      }
    }
  }

  return result;
}

// -------------------------------------------------------------------------
// Main
// -------------------------------------------------------------------------

function main() {
  console.log('[' + MANAGER_NAME + ':uninstall] Hook Manager Uninstall');
  console.log('[' + MANAGER_NAME + ':uninstall] ========================');

  // Step 1: Find latest backup
  var backupDir = findLatestBackup();
  if (!backupDir) {
    console.log('[' + MANAGER_NAME + ':uninstall] ERROR: No backups found for ' + MANAGER_NAME);
    console.log('[' + MANAGER_NAME + ':uninstall] Nothing to uninstall.');
    process.exit(1);
  }

  console.log('[' + MANAGER_NAME + ':uninstall] Found backup: ' + backupDir);

  // Step 2: Read manifest for summary
  var manifestPath = path.join(backupDir, 'manifest.json');
  if (fs.existsSync(manifestPath)) {
    var manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    console.log('[' + MANAGER_NAME + ':uninstall] Backup timestamp: ' + manifest.timestamp);
    console.log('[' + MANAGER_NAME + ':uninstall] Files to restore: ' + manifest.files.length);
    var createdCount = (manifest.created && manifest.created.length) || 0;
    console.log('[' + MANAGER_NAME + ':uninstall] Files to archive: ' + createdCount);
  }

  // Step 3: Restore
  console.log('[' + MANAGER_NAME + ':uninstall] Restoring...');
  var result = restoreFromBackup(backupDir);

  // Step 4: Print results
  console.log('');
  console.log('[' + MANAGER_NAME + ':uninstall] ============================================');
  console.log('[' + MANAGER_NAME + ':uninstall] Uninstall Complete');
  console.log('[' + MANAGER_NAME + ':uninstall] ============================================');

  if (result.restored.length > 0) {
    console.log('[' + MANAGER_NAME + ':uninstall] Restored:');
    for (var i = 0; i < result.restored.length; i++) {
      console.log('[' + MANAGER_NAME + ':uninstall]   ' + result.restored[i]);
    }
  }

  if (result.removed.length > 0) {
    console.log('[' + MANAGER_NAME + ':uninstall] Archived (created by setup):');
    for (var j = 0; j < result.removed.length; j++) {
      console.log('[' + MANAGER_NAME + ':uninstall]   ' + result.removed[j]);
    }
  }

  if (result.errors.length > 0) {
    console.log('[' + MANAGER_NAME + ':uninstall] Errors:');
    for (var k = 0; k < result.errors.length; k++) {
      console.log('[' + MANAGER_NAME + ':uninstall]   ' + result.errors[k]);
    }
  }

  console.log('[' + MANAGER_NAME + ':uninstall] Re-install:');
  console.log('[' + MANAGER_NAME + ':uninstall]   node ~/.claude/skills/' + MANAGER_NAME + '/setup.js');
  console.log('[' + MANAGER_NAME + ':uninstall] ============================================');
  console.log('');
}

// -------------------------------------------------------------------------
// Exports
// -------------------------------------------------------------------------

module.exports = {
  main: main,
  findLatestBackup: findLatestBackup,
  restoreFromBackup: restoreFromBackup
};

if (require.main === module) main();
