#!/usr/bin/env node
/**
 * MCP Manager Uninstall
 * Restores from backup and archives instruction files installed by setup.js.
 * Uses shared setup-utils.js for backup restore and instruction removal.
 *
 * Usage:
 *   node uninstall.js   # Restore from most recent backup
 */

var utils = require('../../super-manager/shared/setup-utils');

var MANAGER_NAME = 'mcp-manager';

// Instruction IDs installed by setup.js
var INSTRUCTION_IDS = [
  'mcp-management',
  'mcpm-only-in-mcp-json',
  'mcpm-reload-flow'
];

function main() {
  console.log('[' + MANAGER_NAME + ':uninstall] Starting...');
  console.log('');

  var restored = [];
  var archived = [];
  var errors = [];

  // ----------------------------------------------------------
  // 1. Find latest backup
  // ----------------------------------------------------------
  var backupDir = utils.findLatestBackup(MANAGER_NAME);

  if (backupDir) {
    console.log('[' + MANAGER_NAME + ':uninstall] Found backup: ' + backupDir);

    // ----------------------------------------------------------
    // 2. Restore files from backup
    // ----------------------------------------------------------
    var restoreResult = utils.restore(backupDir);
    restored = restoreResult.restored;
    errors = restoreResult.errors;

    if (restored.length > 0) {
      console.log('[' + MANAGER_NAME + ':uninstall] Restored ' + restored.length + ' file(s):');
      for (var i = 0; i < restored.length; i++) {
        console.log('[' + MANAGER_NAME + ':uninstall]   ' + restored[i]);
      }
    }

    if (restoreResult.removed.length > 0) {
      console.log('[' + MANAGER_NAME + ':uninstall] Archived ' + restoreResult.removed.length + ' created file(s):');
      for (var j = 0; j < restoreResult.removed.length; j++) {
        console.log('[' + MANAGER_NAME + ':uninstall]   ' + restoreResult.removed[j]);
        archived.push(restoreResult.removed[j]);
      }
    }
  } else {
    console.log('[' + MANAGER_NAME + ':uninstall] No backup found. Archiving instruction files directly.');
  }

  // ----------------------------------------------------------
  // 3. Remove instruction files (archive, not delete)
  //    This catches any instructions not already handled by
  //    the manifest's created[] restore step.
  // ----------------------------------------------------------
  for (var k = 0; k < INSTRUCTION_IDS.length; k++) {
    var id = INSTRUCTION_IDS[k];
    var archivePath = utils.removeInstruction(id, 'UserPromptSubmit');
    if (archivePath) {
      archived.push(archivePath);
      console.log('[' + MANAGER_NAME + ':uninstall] Archived instruction: ' + id + ' -> ' + archivePath);
    }
  }

  // ----------------------------------------------------------
  // 4. Print summary
  // ----------------------------------------------------------
  console.log('');
  console.log('[' + MANAGER_NAME + ':uninstall] ============================================');
  console.log('[' + MANAGER_NAME + ':uninstall] Uninstall Complete');
  console.log('[' + MANAGER_NAME + ':uninstall] ============================================');

  if (restored.length > 0) {
    console.log('[' + MANAGER_NAME + ':uninstall] Restored: ' + restored.length + ' file(s)');
  }

  if (archived.length > 0) {
    console.log('[' + MANAGER_NAME + ':uninstall] Archived: ' + archived.length + ' instruction(s)');
  }

  if (errors.length > 0) {
    console.log('[' + MANAGER_NAME + ':uninstall] Errors:');
    for (var e = 0; e < errors.length; e++) {
      console.log('[' + MANAGER_NAME + ':uninstall]   [!] ' + errors[e]);
    }
  }

  console.log('[' + MANAGER_NAME + ':uninstall] Reinstall:');
  console.log('[' + MANAGER_NAME + ':uninstall]   node ~/.claude/skills/' + MANAGER_NAME + '/setup.js');
  console.log('[' + MANAGER_NAME + ':uninstall] ============================================');
  console.log('');
}

module.exports = { main: main };
if (require.main === module) main();
