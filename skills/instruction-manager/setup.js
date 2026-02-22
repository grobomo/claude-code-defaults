#!/usr/bin/env node
/**
 * Instruction Manager Setup
 *
 * Installs instruction-manager infrastructure:
 *   1. Ensures instruction directories exist
 *   2. Installs writing-instructions.md (meta-instruction)
 *   3. Verifies existing instruction frontmatter health
 *
 * No dependencies - instruction-manager is a leaf node.
 *
 * Usage:
 *   node setup.js
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
  console.log('[instruction-manager:setup] ERROR: Cannot load setup-utils.js');
  console.log('[instruction-manager:setup] Expected at: ' + UTILS_PATH);
  console.log('[instruction-manager:setup] ' + e.message);
  process.exit(1);
}

var MANAGER_NAME = 'instruction-manager';
var p = utils.paths();

// Instruction directories to ensure
var DIRS = [
  path.join(p.instructionsDir, 'UserPromptSubmit'),
  path.join(p.instructionsDir, 'Stop'),
  path.join(p.instructionsDir, 'archive'),
  path.join(p.instructionsDir, 'backups')
];

// ================================================================
// Embedded instruction: writing-instructions.md
// ================================================================

var WRITING_INSTRUCTIONS_CONTENT = '---\n\
id: writing-instructions\n\
name: Writing Instructions\n\
keywords: [instruction, keyword, keywords, trigger, match, matching, rule, rules, meta, write, create, add, new, frontmatter, why]\n\
enabled: true\n\
priority: 10\n\
---\n\
\n\
# Writing Instructions\n\
\n\
## WHY This Exists\n\
\n\
Instructions use keyword matching to load contextual rules. Bad keywords mean rules never fire. This meta-instruction ensures every instruction file is written correctly so the keyword system works reliably.\n\
\n\
## Keyword Rules\n\
\n\
1. **Single words only** - never hyphenated phrases like `getting-started` or `how-it-works`\n\
   - Split into separate words: `getting`, `started`, `how`, `works`\n\
   - User types natural language, not kebab-case\n\
\n\
2. **Short words the user would actually type** - think about what triggers the prompt\n\
   - Good: `bash`, `script`, `write`, `js`\n\
   - Bad: `bash-scripting-safety`, `javascript-heredoc-pattern`\n\
\n\
3. **Include verb forms** - `write`, `writing`, `create`, `add`, `edit`, `fix`, `debug`\n\
\n\
4. **Include synonyms** - `docs` AND `documentation`, `repo` AND `repository`\n\
\n\
5. **No redundant keywords** - if `mcp` covers it, don\'t also add `mcp-server`, `mcp-management`\n\
\n\
6. **5-15 keywords per instruction** - fewer than 5 = too narrow, more than 15 = too noisy\n\
\n\
## Frontmatter Format\n\
\n\
```yaml\n\
---\n\
id: kebab-case-id\n\
name: Human Readable Name\n\
keywords: [word1, word2, word3]\n\
enabled: true\n\
priority: 10\n\
---\n\
```\n\
\n\
- `id` matches filename (without .md)\n\
- `priority` default 10, use 100 for critical rules (like review-instructions)\n\
- `enabled` defaults to true\n\
\n\
## Content Structure\n\
\n\
Every instruction MUST have:\n\
\n\
1. **Title** - `# Short Name`\n\
2. **WHY** section - why this rule exists (not just what to do)\n\
3. **What To Do** - concrete actions\n\
4. **Do NOT** (optional) - common mistakes to avoid\n\
\n\
## Where Instructions Live\n\
\n\
Single location: `~/.claude/instructions/UserPromptSubmit/`\n\
\n\
instruction-manager reads/writes here directly. No copies elsewhere.\n\
\n\
## Keyword Selection Process\n\
\n\
When creating a new instruction, review the current chat history to find what words the user actually typed that should have triggered this instruction. Those words become keywords.\n\
\n\
1. **Look at what the user typed** - the exact words from the conversation that led to needing this instruction\n\
2. **Be generous** - better to match too often than miss when needed\n\
3. **Check existing instructions** - run `ls ~/.claude/instructions/UserPromptSubmit/` to see what\'s already covered\n\
\n\
## Keywords vs Patterns\n\
\n\
- **Keywords** = single words for UserPromptSubmit matching (e.g. `bash`, `mcp`, `deploy`)\n\
- **Patterns** = regex for Stop hook response matching (e.g. `(should|want)\\s.{0,20}fix`)\n\
- NEVER use multi-word keywords. Use patterns for phrase matching.\n\
- `add_item()` auto-sanitizes: splits multi-word and hyphenated keywords into singles.\n\
\n\
## Do NOT\n\
\n\
- Do NOT use multi-word or hyphenated keywords (enforced by `_sanitize_keywords()`)\n\
- Do NOT put instructions in CLAUDE.md (use instruction files)\n\
- Do NOT create hooks when an instruction would work\n\
- Do NOT skip the WHY section\n\
- Do NOT maintain duplicate copies of instructions anywhere\n';

// ================================================================
// Step 1: Ensure directories
// ================================================================

function ensureDirectories() {
  var created = [];
  var existed = [];
  for (var i = 0; i < DIRS.length; i++) {
    if (fs.existsSync(DIRS[i])) {
      existed.push(DIRS[i]);
    } else {
      fs.mkdirSync(DIRS[i], { recursive: true });
      created.push(DIRS[i]);
    }
  }
  return { created: created, existed: existed };
}

// ================================================================
// Step 2: Install writing-instructions.md
// ================================================================

function installWritingInstructions(backupDir) {
  var result = utils.installInstruction({
    id: 'writing-instructions',
    content: WRITING_INSTRUCTIONS_CONTENT,
    event: 'UserPromptSubmit'
  });

  // Track if we created a new file
  if (result.method !== 'skipped' && backupDir) {
    utils.trackCreatedFile(backupDir, result.path);
  }

  return result;
}

// ================================================================
// Step 3: Verify frontmatter health of all instructions
// ================================================================

function verifyFrontmatter() {
  var results = { healthy: [], warnings: [] };
  var events = ['UserPromptSubmit', 'Stop'];

  for (var e = 0; e < events.length; e++) {
    var eventDir = path.join(p.instructionsDir, events[e]);
    if (!fs.existsSync(eventDir)) continue;

    var files;
    try {
      files = fs.readdirSync(eventDir);
    } catch (err) {
      results.warnings.push('Cannot read ' + eventDir + ': ' + err.message);
      continue;
    }

    for (var f = 0; f < files.length; f++) {
      if (!files[f].endsWith('.md')) continue;
      var filePath = path.join(eventDir, files[f]);
      var content;
      try {
        content = fs.readFileSync(filePath, 'utf8');
      } catch (err) {
        results.warnings.push(files[f] + ': cannot read (' + err.message + ')');
        continue;
      }

      var issues = [];

      // Check frontmatter exists
      if (!content.startsWith('---')) {
        issues.push('no frontmatter');
      } else {
        var endIdx = content.indexOf('---', 3);
        if (endIdx === -1) {
          issues.push('malformed frontmatter (no closing ---)');
        } else {
          var fm = content.substring(3, endIdx);

          // Check required fields
          if (fm.indexOf('id:') === -1) {
            issues.push('missing id');
          }
          if (fm.indexOf('enabled:') === -1) {
            issues.push('missing enabled');
          }

          // UserPromptSubmit needs keywords, Stop needs keywords or pattern
          if (events[e] === 'UserPromptSubmit') {
            if (fm.indexOf('keywords:') === -1) {
              issues.push('missing keywords');
            }
          } else if (events[e] === 'Stop') {
            if (fm.indexOf('keywords:') === -1 && fm.indexOf('pattern:') === -1) {
              issues.push('missing keywords or pattern');
            }
          }
        }
      }

      if (issues.length > 0) {
        results.warnings.push(events[e] + '/' + files[f] + ': ' + issues.join(', '));
      } else {
        results.healthy.push(events[e] + '/' + files[f]);
      }
    }
  }

  return results;
}

// ================================================================
// Main
// ================================================================

function main() {
  console.log('');
  console.log('[instruction-manager:setup] Starting...');
  console.log('');

  // -- Backup --
  console.log('[1/3] Creating backup...');
  var filesToBackup = [p.settingsJson];

  // Also backup writing-instructions.md if it exists
  var existingWI = path.join(p.instructionsDir, 'UserPromptSubmit', 'writing-instructions.md');
  if (fs.existsSync(existingWI)) {
    filesToBackup.push(existingWI);
  }

  var bk = utils.backup(MANAGER_NAME, filesToBackup);
  console.log('[instruction-manager:setup]   Backup: ' + bk.backupDir);

  // -- Step 1: Directories --
  console.log('[2/3] Ensuring directories...');
  var dirs = ensureDirectories();
  if (dirs.created.length > 0) {
    for (var i = 0; i < dirs.created.length; i++) {
      console.log('[instruction-manager:setup]   Created: ' + path.relative(CLAUDE_DIR, dirs.created[i]));
      utils.trackCreatedFile(bk.backupDir, dirs.created[i]);
    }
  }
  if (dirs.existed.length > 0) {
    console.log('[instruction-manager:setup]   ' + dirs.existed.length + ' dir(s) already existed');
  }

  // -- Step 2: Install instruction --
  console.log('[3/3] Installing instructions...');
  var instResult = installWritingInstructions(bk.backupDir);
  console.log('[instruction-manager:setup]   writing-instructions.md: ' + instResult.method);

  // -- Verify frontmatter health --
  console.log('');
  console.log('[instruction-manager:setup] Verifying frontmatter health...');
  var fmResults = verifyFrontmatter();
  console.log('[instruction-manager:setup]   Healthy: ' + fmResults.healthy.length + ' instruction(s)');
  if (fmResults.warnings.length > 0) {
    console.log('[instruction-manager:setup]   Warnings: ' + fmResults.warnings.length);
    for (var w = 0; w < fmResults.warnings.length; w++) {
      console.log('[instruction-manager:setup]     [!] ' + fmResults.warnings[w]);
    }
  }

  // -- Summary --
  var warnings = [];
  if (fmResults.warnings.length > 0) {
    warnings.push(fmResults.warnings.length + ' instruction(s) have frontmatter issues');
  }

  utils.printSummary({
    manager: MANAGER_NAME,
    backup: bk,
    instructions: [instResult],
    hooks: [],
    warnings: warnings
  });
}

// ================================================================
// Exports
// ================================================================

module.exports = {
  main: main,
  ensureDirectories: ensureDirectories,
  installWritingInstructions: installWritingInstructions,
  verifyFrontmatter: verifyFrontmatter,
  WRITING_INSTRUCTIONS_CONTENT: WRITING_INSTRUCTIONS_CONTENT
};

if (require.main === module) main();
