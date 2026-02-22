#!/usr/bin/env node
/**
 * @module hook-manager/setup
 * Hook Manager Setup - installs instruction files that teach Claude about hook conventions.
 * Hook-manager IS the hook expert so it doesn't need hooks itself.
 *
 * WHY: Without this instruction file, Claude re-discovers hook contracts (stdin/stdout
 * formats, matcher rules, sync-only requirement) through trial and error every session.
 * This setup ensures the conventions are always loaded when prompts mention hooks.
 *
 * Usage:
 *   node setup.js           # Install instruction files + defensive backup
 */
var fs = require('fs');
var path = require('path');
var os = require('os');

var HOME = os.homedir();
var CLAUDE_DIR = path.join(HOME, '.claude');
var SETTINGS_JSON = path.join(CLAUDE_DIR, 'settings.json');
var INSTRUCTIONS_DIR = path.join(CLAUDE_DIR, 'instructions');
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
// Instruction content
// -------------------------------------------------------------------------

var HOOK_CONVENTIONS_ID = 'hook-conventions';
var HOOK_CONVENTIONS_EVENT = 'UserPromptSubmit';

var HOOK_CONVENTIONS_CONTENT = [
  '---',
  'id: hook-conventions',
  'name: Hook Conventions',
  'keywords: [hook, hooks, settings.json, PreToolUse, PostToolUse, UserPromptSubmit, Stop]',
  'enabled: true',
  'description: Hook format and contract rules',
  '---',
  '',
  '# Hook Conventions',
  '',
  '- Hooks are ALWAYS synchronous Node.js (var, fs.readFileSync, no async/await)',
  '- stdin contract varies by event type - check hook-manager SKILL.md for exact format',
  '- Events WITHOUT matcher (UserPromptSubmit, Stop): OMIT matcher field entirely',
  '- Events WITH matcher (PreToolUse, PostToolUse): matcher is a string like "Bash" or "Skill|Task"',
  '- Stop hooks output: {"decision":"block","reason":"..."} to block, or nothing/exit 0 to allow',
  '- PreToolUse hooks output: exit 2 to deny tool, exit 0 to allow',
  '- ALWAYS use hook-manager skill when creating or modifying hooks'
].join('\n');

// -------------------------------------------------------------------------
// Backup
// -------------------------------------------------------------------------

/**
 * Create defensive backup of settings.json and any existing instruction file.
 * @returns {{ backupDir: string, manifest: object }|null}
 */
function createBackup() {
  var filesToBackup = [];

  // Always backup settings.json defensively
  if (fs.existsSync(SETTINGS_JSON)) {
    filesToBackup.push(SETTINGS_JSON);
  }

  // Backup existing hook-conventions.md if it exists
  var existingInstruction = path.join(INSTRUCTIONS_DIR, HOOK_CONVENTIONS_EVENT, HOOK_CONVENTIONS_ID + '.md');
  if (fs.existsSync(existingInstruction)) {
    filesToBackup.push(existingInstruction);
  }

  if (filesToBackup.length === 0) {
    return null;
  }

  // Use shared utils if available, otherwise inline backup
  if (utils) {
    return utils.backup(MANAGER_NAME, filesToBackup);
  }

  // Inline fallback backup
  var ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  var backupDir = path.join(CLAUDE_DIR, 'backups', MANAGER_NAME, ts);
  fs.mkdirSync(backupDir, { recursive: true });

  var files = [];
  for (var i = 0; i < filesToBackup.length; i++) {
    var src = filesToBackup[i];
    var relName = path.basename(src);
    // Preserve subdirectory structure for instruction files
    if (src.indexOf(path.join('instructions', 'UserPromptSubmit')) !== -1) {
      relName = path.join('instructions', 'UserPromptSubmit', path.basename(src));
      fs.mkdirSync(path.join(backupDir, 'instructions', 'UserPromptSubmit'), { recursive: true });
    }
    fs.copyFileSync(src, path.join(backupDir, relName));
    files.push({ original: src, backed: relName });
  }

  var manifest = {
    manager: MANAGER_NAME,
    timestamp: ts,
    platform: process.platform,
    files: files,
    created: []
  };
  fs.writeFileSync(path.join(backupDir, 'manifest.json'), JSON.stringify(manifest, null, 2));
  return { backupDir: backupDir, manifest: manifest };
}

// -------------------------------------------------------------------------
// Install instruction file
// -------------------------------------------------------------------------

/**
 * Install the hook-conventions instruction file.
 * Uses instruction-manager via shared utils if available, direct write otherwise.
 * @returns {{ method: string, path: string, fallback: boolean }}
 */
function installInstructionFile() {
  if (utils) {
    return utils.installInstruction({
      id: HOOK_CONVENTIONS_ID,
      content: HOOK_CONVENTIONS_CONTENT,
      event: HOOK_CONVENTIONS_EVENT
    });
  }

  // Direct write fallback
  var destDir = path.join(INSTRUCTIONS_DIR, HOOK_CONVENTIONS_EVENT);
  var destPath = path.join(destDir, HOOK_CONVENTIONS_ID + '.md');

  fs.mkdirSync(destDir, { recursive: true });

  // Skip if identical content already exists
  if (fs.existsSync(destPath)) {
    var existing = fs.readFileSync(destPath, 'utf8');
    if (existing === HOOK_CONVENTIONS_CONTENT) {
      return { method: 'skipped', path: destPath, fallback: false };
    }
  }

  fs.writeFileSync(destPath, HOOK_CONVENTIONS_CONTENT, 'utf8');
  return { method: 'direct-write', path: destPath, fallback: true };
}

// -------------------------------------------------------------------------
// Track created files in manifest
// -------------------------------------------------------------------------

/**
 * Track a file created by setup for clean uninstall.
 * @param {string} backupDir
 * @param {string} filePath
 */
function trackCreated(backupDir, filePath) {
  if (utils) {
    utils.trackCreatedFile(backupDir, filePath);
    return;
  }

  // Inline fallback
  var manifestPath = path.join(backupDir, 'manifest.json');
  if (!fs.existsSync(manifestPath)) return;
  var manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  if (!manifest.created) manifest.created = [];
  if (manifest.created.indexOf(filePath) === -1) {
    manifest.created.push(filePath);
  }
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
}

// -------------------------------------------------------------------------
// Check dependencies
// -------------------------------------------------------------------------

/**
 * Check if instruction-manager is installed.
 * @returns {{ installed: boolean, skillDir: string }}
 */
function checkInstructionManager() {
  if (utils) {
    return utils.checkDependency('instruction-manager');
  }

  var skillDir = path.join(CLAUDE_DIR, 'skills', 'instruction-manager');
  var skillMd = path.join(skillDir, 'SKILL.md');
  return {
    installed: fs.existsSync(skillMd),
    skillDir: skillDir
  };
}

// -------------------------------------------------------------------------
// Summary printer
// -------------------------------------------------------------------------

/**
 * Print standardized setup summary.
 * @param {object} opts
 */
function printSetupSummary(opts) {
  if (utils) {
    utils.printSummary(opts);
    return;
  }

  // Inline fallback
  console.log('');
  console.log('[' + MANAGER_NAME + ':setup] ============================================');
  console.log('[' + MANAGER_NAME + ':setup] Installation Complete');
  console.log('[' + MANAGER_NAME + ':setup] ============================================');

  if (opts.backup) {
    console.log('[' + MANAGER_NAME + ':setup] Backup: ' + opts.backup.backupDir);
  }

  if (opts.instructions && opts.instructions.length > 0) {
    console.log('[' + MANAGER_NAME + ':setup] Instructions:');
    for (var i = 0; i < opts.instructions.length; i++) {
      var inst = opts.instructions[i];
      console.log('[' + MANAGER_NAME + ':setup]   ' + inst.method + ': ' + path.basename(inst.path));
    }
  }

  if (opts.warnings && opts.warnings.length > 0) {
    console.log('[' + MANAGER_NAME + ':setup] Recommendations:');
    for (var w = 0; w < opts.warnings.length; w++) {
      console.log('[' + MANAGER_NAME + ':setup]   [!] ' + opts.warnings[w]);
    }
  }

  console.log('[' + MANAGER_NAME + ':setup] Uninstall:');
  console.log('[' + MANAGER_NAME + ':setup]   node ~/.claude/skills/' + MANAGER_NAME + '/uninstall.js');
  console.log('[' + MANAGER_NAME + ':setup] ============================================');
  console.log('');
}

// -------------------------------------------------------------------------
// Main
// -------------------------------------------------------------------------

function main() {
  console.log('[' + MANAGER_NAME + ':setup] Hook Manager Setup');
  console.log('[' + MANAGER_NAME + ':setup] ====================');

  var warnings = [];

  // Step 1: Check dependencies
  console.log('[' + MANAGER_NAME + ':setup] [1/3] Checking dependencies...');
  var imStatus = checkInstructionManager();
  if (imStatus.installed) {
    console.log('[' + MANAGER_NAME + ':setup]   instruction-manager: installed');
  } else {
    console.log('[' + MANAGER_NAME + ':setup]   instruction-manager: not found (using direct write)');
    warnings.push('Install instruction-manager for better keyword matching');
  }

  // Step 2: Backup
  console.log('[' + MANAGER_NAME + ':setup] [2/3] Creating backup...');
  var backupResult = createBackup();
  if (backupResult) {
    console.log('[' + MANAGER_NAME + ':setup]   Backed up ' + backupResult.manifest.files.length + ' file(s) to ' + backupResult.backupDir);
  } else {
    console.log('[' + MANAGER_NAME + ':setup]   No existing files to backup');
  }

  // Step 3: Install instruction file
  console.log('[' + MANAGER_NAME + ':setup] [3/3] Installing instruction file...');
  var instResult = installInstructionFile();
  console.log('[' + MANAGER_NAME + ':setup]   ' + instResult.method + ': ' + path.basename(instResult.path));

  // Track created file in manifest for uninstall
  if (backupResult && instResult.method !== 'skipped') {
    trackCreated(backupResult.backupDir, instResult.path);
  }

  if (instResult.fallback) {
    warnings.push('Instruction installed via direct write (instruction-manager not available)');
  }

  // Print summary
  printSetupSummary({
    manager: MANAGER_NAME,
    backup: backupResult,
    instructions: [instResult],
    hooks: [],
    warnings: warnings
  });
}

// -------------------------------------------------------------------------
// Exports
// -------------------------------------------------------------------------

module.exports = {
  main: main,
  createBackup: createBackup,
  installInstructionFile: installInstructionFile,
  HOOK_CONVENTIONS_ID: HOOK_CONVENTIONS_ID,
  HOOK_CONVENTIONS_EVENT: HOOK_CONVENTIONS_EVENT,
  HOOK_CONVENTIONS_CONTENT: HOOK_CONVENTIONS_CONTENT
};

if (require.main === module) main();
