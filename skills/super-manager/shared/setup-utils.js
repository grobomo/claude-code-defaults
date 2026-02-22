#!/usr/bin/env node
/**
 * @module setup-utils
 * Shared utilities for all sub-manager setup/uninstall scripts.
 * Pure Node.js (fs, path, os) - no npm dependencies.
 *
 * Every sub-manager setup.js imports this for:
 *   - backup/restore with timestamped manifests
 *   - dependency checking (is instruction-manager installed?)
 *   - instruction file installation (via instruction-manager or fallback)
 *   - hook installation (via hook-manager or fallback)
 *   - settings.json hook merging (additive, never destructive)
 *   - manifest tracking (what was installed, for uninstall)
 */
var fs = require('fs');
var path = require('path');
var os = require('os');

var HOME = os.homedir();
var CLAUDE_DIR = path.join(HOME, '.claude');
var HOOKS_DIR = path.join(CLAUDE_DIR, 'hooks');
var SKILLS_DIR = path.join(CLAUDE_DIR, 'skills');
var BACKUPS_DIR = path.join(CLAUDE_DIR, 'backups');
var INSTRUCTIONS_DIR = path.join(CLAUDE_DIR, 'instructions');
var SETTINGS_JSON = path.join(CLAUDE_DIR, 'settings.json');

// -------------------------------------------------------------------------
// Path helpers
// -------------------------------------------------------------------------

function paths() {
  return {
    home: HOME,
    claudeDir: CLAUDE_DIR,
    hooksDir: HOOKS_DIR,
    skillsDir: SKILLS_DIR,
    backupsDir: BACKUPS_DIR,
    instructionsDir: INSTRUCTIONS_DIR,
    settingsJson: SETTINGS_JSON
  };
}

// -------------------------------------------------------------------------
// Dependency checking
// -------------------------------------------------------------------------

/**
 * Check if a sub-manager skill is installed (has SKILL.md)
 * @param {string} managerName - e.g. 'hook-manager', 'instruction-manager'
 * @returns {{ installed: boolean, skillDir: string, hasSetup: boolean }}
 */
function checkDependency(managerName) {
  var skillDir = path.join(SKILLS_DIR, managerName);
  var skillMd = path.join(skillDir, 'SKILL.md');
  var setupJs = path.join(skillDir, 'setup.js');
  return {
    installed: fs.existsSync(skillMd),
    skillDir: skillDir,
    hasSetup: fs.existsSync(setupJs)
  };
}

// -------------------------------------------------------------------------
// Backup / Restore
// -------------------------------------------------------------------------

/**
 * Create timestamped backup of specified files before making changes.
 * @param {string} managerName - e.g. 'mcp-manager'
 * @param {string[]} filePaths - absolute paths to back up
 * @returns {{ backupDir: string, manifest: object }}
 */
function backup(managerName, filePaths) {
  var ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  var backupDir = path.join(BACKUPS_DIR, managerName, ts);
  fs.mkdirSync(backupDir, { recursive: true });

  var files = [];
  for (var i = 0; i < filePaths.length; i++) {
    var src = filePaths[i];
    if (!fs.existsSync(src)) continue;
    var relName = path.basename(src);
    // Preserve subdirectory structure for instruction files
    if (src.indexOf(path.join('instructions', 'UserPromptSubmit')) !== -1) {
      relName = path.join('instructions', 'UserPromptSubmit', path.basename(src));
      fs.mkdirSync(path.join(backupDir, 'instructions', 'UserPromptSubmit'), { recursive: true });
    } else if (src.indexOf(path.join('instructions', 'Stop')) !== -1) {
      relName = path.join('instructions', 'Stop', path.basename(src));
      fs.mkdirSync(path.join(backupDir, 'instructions', 'Stop'), { recursive: true });
    }
    fs.copyFileSync(src, path.join(backupDir, relName));
    files.push({ original: src, backed: relName });
  }

  var manifest = {
    manager: managerName,
    timestamp: ts,
    platform: process.platform,
    files: files,
    created: []  // tracks files created by setup (for uninstall cleanup)
  };
  fs.writeFileSync(path.join(backupDir, 'manifest.json'), JSON.stringify(manifest, null, 2));
  return { backupDir: backupDir, manifest: manifest };
}

/**
 * Find the latest backup for a manager.
 * @param {string} managerName
 * @returns {string|null} path to latest backup dir, or null
 */
function findLatestBackup(managerName) {
  var managerBackups = path.join(BACKUPS_DIR, managerName);
  if (!fs.existsSync(managerBackups)) return null;
  var dirs = fs.readdirSync(managerBackups).sort().reverse();
  return dirs.length > 0 ? path.join(managerBackups, dirs[0]) : null;
}

/**
 * Restore files from a backup manifest.
 * @param {string} backupDir - path to the backup directory
 * @returns {{ restored: string[], removed: string[], errors: string[] }}
 */
function restore(backupDir) {
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

  // Remove files that were created by setup (not pre-existing)
  if (manifest.created && manifest.created.length > 0) {
    for (var j = 0; j < manifest.created.length; j++) {
      var f = manifest.created[j];
      if (fs.existsSync(f)) {
        // Archive instead of delete
        var archiveDir = path.join(CLAUDE_DIR, 'archive', manifest.manager);
        fs.mkdirSync(archiveDir, { recursive: true });
        var archiveName = path.basename(f) + '.' + new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        fs.renameSync(f, path.join(archiveDir, archiveName));
        result.removed.push(f);
      }
    }
  }

  return result;
}

// -------------------------------------------------------------------------
// Instruction file installation
// -------------------------------------------------------------------------

/**
 * Install an instruction file. Uses instruction-manager if available,
 * otherwise writes directly to ~/.claude/instructions/<event>/.
 *
 * @param {object} opts
 * @param {string} opts.id - instruction id
 * @param {string} opts.content - full markdown content with frontmatter
 * @param {string} opts.event - 'UserPromptSubmit' or 'Stop'
 * @returns {{ method: string, path: string, fallback: boolean }}
 */
function installInstruction(opts) {
  var event = opts.event || 'UserPromptSubmit';
  var destDir = path.join(INSTRUCTIONS_DIR, event);
  var destPath = path.join(destDir, opts.id + '.md');

  // Always write to disk (instruction-manager reads from same location)
  fs.mkdirSync(destDir, { recursive: true });

  // Skip if identical content already exists
  if (fs.existsSync(destPath)) {
    var existing = fs.readFileSync(destPath, 'utf8');
    if (existing === opts.content) {
      return { method: 'skipped', path: destPath, fallback: false };
    }
  }

  fs.writeFileSync(destPath, opts.content, 'utf8');

  var imInstalled = checkDependency('instruction-manager').installed;
  return {
    method: imInstalled ? 'instruction-manager' : 'direct-write',
    path: destPath,
    fallback: !imInstalled
  };
}

/**
 * Remove an instruction file (archive, never delete).
 * @param {string} id - instruction id
 * @param {string} event - 'UserPromptSubmit' or 'Stop'
 * @returns {string|null} archive path, or null if not found
 */
function removeInstruction(id, event) {
  event = event || 'UserPromptSubmit';
  var srcPath = path.join(INSTRUCTIONS_DIR, event, id + '.md');
  if (!fs.existsSync(srcPath)) return null;

  var archiveDir = path.join(INSTRUCTIONS_DIR, 'archive');
  fs.mkdirSync(archiveDir, { recursive: true });
  var ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  var archivePath = path.join(archiveDir, id + '.' + ts + '.md');
  fs.renameSync(srcPath, archivePath);
  return archivePath;
}

// -------------------------------------------------------------------------
// Routing instruction template (auto-create during skill/MCP setup)
// -------------------------------------------------------------------------

/**
 * Generate and install a routing instruction that teaches Claude WHEN to use
 * a specific skill or MCP server instead of generic tools (WebFetch, Bash, etc).
 *
 * Call this from any skill or MCP setup script. It uses installInstruction()
 * internally, with fallback to direct file write if instruction-manager
 * is not installed.
 *
 * @param {object} opts
 * @param {string} opts.toolName    - skill or MCP name, e.g. 'wiki-api'
 * @param {string} opts.toolType    - 'skill' or 'mcp'
 * @param {string[]} opts.keywords  - trigger keywords for this instruction
 * @param {string} opts.description - one-line what the tool does
 * @param {string} opts.whenToUse   - when Claude should reach for this tool
 * @param {string} [opts.fallback]  - optional fallback tool name
 * @param {string} [opts.neverUse]  - tool to never use for this case (e.g. 'WebFetch')
 * @param {string} [opts.whyNot]    - why the generic tool fails (e.g. 'hits login redirect')
 * @param {string} [opts.howToUse]  - brief usage example or invocation pattern
 * @returns {{ method: string, path: string, fallback: boolean }}
 */
function ensureRoutingInstruction(opts) {
  var id = opts.toolName + '-routing';
  var toolLabel = opts.toolType === 'mcp' ? 'MCP server' : 'skill';
  var fallbackLine = opts.fallback
    ? '\n3. **Fallback to ' + opts.fallback + '** if the ' + toolLabel + ' fails'
    : '';
  var neverLine = opts.neverUse
    ? '\n4. **Never use ' + opts.neverUse + '** for this' + (opts.whyNot ? ' -- ' + opts.whyNot : '')
    : '';
  var howLine = opts.howToUse
    ? '\n\n## How\n```\n' + opts.howToUse + '\n```'
    : '';

  var body = [
    '---',
    'id: ' + id,
    'name: ' + opts.toolName + ' Routing',
    'keywords: [' + opts.keywords.join(', ') + ']',
    'enabled: true',
    'priority: 10',
    '---',
    '',
    '# ' + opts.toolName + ' Routing',
    '',
    '## WHY',
    opts.description + '. The ' + opts.toolName + ' ' + toolLabel + ' is already configured',
    'and authenticated. Using it is faster and more reliable than generic tools.',
    '',
    '## Rule',
    'When ' + opts.whenToUse + ':',
    '',
    '1. **Use ' + opts.toolName + ' ' + toolLabel + '** (preferred)',
    '2. **Invoke via ' + (opts.toolType === 'skill' ? 'Skill tool' : 'MCP tool calls') + '**' + fallbackLine + neverLine,
    howLine,
    ''
  ].join('\n');

  return installInstruction({ id: id, content: body, event: 'UserPromptSubmit' });
}

// -------------------------------------------------------------------------
// Hook installation
// -------------------------------------------------------------------------

/**
 * Install a hook script file and register it in settings.json.
 * Uses hook-manager format conventions.
 *
 * @param {object} opts
 * @param {string} opts.filename - hook script filename (e.g. 'my-hook.js')
 * @param {string} opts.content - hook script source code
 * @param {string} opts.event - 'UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'Stop', etc.
 * @param {string} [opts.matcher] - matcher string for Pre/PostToolUse events (omit for UPS/Stop)
 * @returns {{ installed: boolean, registered: boolean, path: string, fallback: boolean }}
 */
function installHook(opts) {
  var destPath = path.join(HOOKS_DIR, opts.filename);
  var result = { installed: false, registered: false, path: destPath, fallback: false };

  // Write hook script (skip if identical)
  fs.mkdirSync(HOOKS_DIR, { recursive: true });
  if (fs.existsSync(destPath)) {
    var existing = fs.readFileSync(destPath, 'utf8');
    if (existing === opts.content) {
      result.installed = true; // already there
    } else {
      // Archive old version, install new
      var archiveDir = path.join(CLAUDE_DIR, 'archive', 'hooks');
      fs.mkdirSync(archiveDir, { recursive: true });
      var ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      fs.copyFileSync(destPath, path.join(archiveDir, opts.filename + '.' + ts));
      fs.writeFileSync(destPath, opts.content, 'utf8');
      result.installed = true;
    }
  } else {
    fs.writeFileSync(destPath, opts.content, 'utf8');
    result.installed = true;
  }

  // Register in settings.json
  result.registered = addHookToSettings(opts.event, opts.filename, opts.matcher);
  result.fallback = !checkDependency('hook-manager').installed;
  return result;
}

/**
 * Add a hook entry to settings.json (additive merge, never destructive).
 * Follows hook-manager format: settings.hooks[event] = [{ matcher, hooks: [{ type, command }] }]
 *
 * @param {string} event
 * @param {string} filename
 * @param {string} [matcher]
 * @returns {boolean} true if added, false if already exists
 */
function addHookToSettings(event, filename, matcher) {
  var settings;
  try {
    settings = JSON.parse(fs.readFileSync(SETTINGS_JSON, 'utf8'));
  } catch (e) {
    settings = {};
  }

  if (!settings.hooks) settings.hooks = {};
  if (!settings.hooks[event]) settings.hooks[event] = [];

  var command = 'node "' + path.join(HOOKS_DIR, filename).replace(/\\/g, '/') + '"';

  // Check if already registered
  for (var i = 0; i < settings.hooks[event].length; i++) {
    var group = settings.hooks[event][i];
    if (!group.hooks) continue;
    for (var j = 0; j < group.hooks.length; j++) {
      if (group.hooks[j].command && group.hooks[j].command.indexOf(filename) !== -1) {
        return false; // already registered
      }
    }
  }

  // Find or create matcher group
  var targetMatcher = matcher || '*';
  var matcherGroup = null;
  for (var k = 0; k < settings.hooks[event].length; k++) {
    if (settings.hooks[event][k].matcher === targetMatcher) {
      matcherGroup = settings.hooks[event][k];
      break;
    }
  }
  if (!matcherGroup) {
    matcherGroup = { matcher: targetMatcher, hooks: [] };
    settings.hooks[event].push(matcherGroup);
  }

  matcherGroup.hooks.push({ type: 'command', command: command });
  fs.writeFileSync(SETTINGS_JSON, JSON.stringify(settings, null, 2), 'utf8');
  return true;
}

/**
 * Remove a hook from settings.json by filename.
 * @param {string} event
 * @param {string} filename
 * @returns {boolean} true if removed
 */
function removeHookFromSettings(event, filename) {
  var settings;
  try {
    settings = JSON.parse(fs.readFileSync(SETTINGS_JSON, 'utf8'));
  } catch (e) {
    return false;
  }

  if (!settings.hooks || !settings.hooks[event]) return false;

  var removed = false;
  for (var i = 0; i < settings.hooks[event].length; i++) {
    var group = settings.hooks[event][i];
    if (!group.hooks) continue;
    group.hooks = group.hooks.filter(function (h) {
      if (h.command && h.command.indexOf(filename) !== -1) {
        removed = true;
        return false;
      }
      return true;
    });
  }

  // Clean up empty groups
  settings.hooks[event] = settings.hooks[event].filter(function (g) {
    return g.hooks && g.hooks.length > 0;
  });

  if (removed) {
    fs.writeFileSync(SETTINGS_JSON, JSON.stringify(settings, null, 2), 'utf8');
  }
  return removed;
}

// -------------------------------------------------------------------------
// Manifest tracking (what setup created, for clean uninstall)
// -------------------------------------------------------------------------

/**
 * Record a file that setup created (not pre-existing) in the manifest.
 * Called during setup after creating new files.
 * @param {string} backupDir
 * @param {string} filePath - absolute path of created file
 */
function trackCreatedFile(backupDir, filePath) {
  var manifestPath = path.join(backupDir, 'manifest.json');
  if (!fs.existsSync(manifestPath)) return;
  var manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  if (!manifest.created) manifest.created = [];
  if (manifest.created.indexOf(filePath) === -1) {
    manifest.created.push(filePath);
  }
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2), 'utf8');
}

// -------------------------------------------------------------------------
// Summary printer
// -------------------------------------------------------------------------

/**
 * Print a standardized setup summary.
 * @param {object} opts
 * @param {string} opts.manager - manager name
 * @param {object} opts.backup - backup result
 * @param {object[]} opts.instructions - instruction install results
 * @param {object[]} opts.hooks - hook install results
 * @param {string[]} opts.warnings - fallback warnings
 */
function printSummary(opts) {
  console.log('');
  console.log('[' + opts.manager + ':setup] ============================================');
  console.log('[' + opts.manager + ':setup] Installation Complete');
  console.log('[' + opts.manager + ':setup] ============================================');

  if (opts.backup) {
    console.log('[' + opts.manager + ':setup] Backup: ' + opts.backup.backupDir);
  }

  if (opts.instructions && opts.instructions.length > 0) {
    console.log('[' + opts.manager + ':setup] Instructions:');
    for (var i = 0; i < opts.instructions.length; i++) {
      var inst = opts.instructions[i];
      console.log('[' + opts.manager + ':setup]   ' + inst.method + ': ' + path.basename(inst.path));
    }
  }

  if (opts.hooks && opts.hooks.length > 0) {
    console.log('[' + opts.manager + ':setup] Hooks:');
    for (var h = 0; h < opts.hooks.length; h++) {
      var hk = opts.hooks[h];
      var status = hk.registered ? 'registered' : 'exists';
      console.log('[' + opts.manager + ':setup]   ' + status + ': ' + path.basename(hk.path));
    }
  }

  if (opts.warnings && opts.warnings.length > 0) {
    console.log('[' + opts.manager + ':setup] Recommendations:');
    for (var w = 0; w < opts.warnings.length; w++) {
      console.log('[' + opts.manager + ':setup]   [!] ' + opts.warnings[w]);
    }
  }

  console.log('[' + opts.manager + ':setup] Uninstall:');
  console.log('[' + opts.manager + ':setup]   node ~/.claude/skills/' + opts.manager + '/uninstall.js');
  console.log('[' + opts.manager + ':setup] ============================================');
  console.log('');
}

// -------------------------------------------------------------------------
// Exports
// -------------------------------------------------------------------------

module.exports = {
  paths: paths,
  checkDependency: checkDependency,
  backup: backup,
  findLatestBackup: findLatestBackup,
  restore: restore,
  installInstruction: installInstruction,
  ensureRoutingInstruction: ensureRoutingInstruction,
  removeInstruction: removeInstruction,
  installHook: installHook,
  addHookToSettings: addHookToSettings,
  removeHookFromSettings: removeHookFromSettings,
  trackCreatedFile: trackCreatedFile,
  printSummary: printSummary,
  // Constants
  HOME: HOME,
  CLAUDE_DIR: CLAUDE_DIR,
  HOOKS_DIR: HOOKS_DIR,
  SKILLS_DIR: SKILLS_DIR,
  BACKUPS_DIR: BACKUPS_DIR,
  INSTRUCTIONS_DIR: INSTRUCTIONS_DIR,
  SETTINGS_JSON: SETTINGS_JSON
};
