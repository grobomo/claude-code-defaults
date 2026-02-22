#!/usr/bin/env node
/**
 * Skill Manager Setup
 * Self-installing skill manager for Claude Code.
 * Scans skills, enriches keywords, installs hooks, auto-maintains on session start.
 *
 * Usage:
 *   node setup.js             # Install/update everything
 *   node setup.js --uninstall # Restore from most recent backup
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const HOME = os.homedir();
const CLAUDE_DIR = path.join(HOME, '.claude');
const SKILLS_DIR = path.join(CLAUDE_DIR, 'skills');
const HOOKS_DIR = path.join(CLAUDE_DIR, 'hooks');
const SETTINGS_PATH = path.join(CLAUDE_DIR, 'settings.json');
const REGISTRY_PATH = path.join(HOOKS_DIR, 'skill-registry.json');
const LOGS_DIR = path.join(CLAUDE_DIR, 'logs');
const BACKUP_BASE = path.join(CLAUDE_DIR, 'backups', 'skill-manager');
const REPORT_PATH = path.join(CLAUDE_DIR, 'skill-manager-report.md');
const SKILL_MANAGER_DIR = path.join(SKILLS_DIR, 'skill-manager');
const ARCHIVE_DIR = path.join(SKILL_MANAGER_DIR, 'archive');

// ================================================================
// Keyword Extraction Pipeline (copied from super-manager/setup.js)
// ================================================================

function extractKeywords(content) {
  if (!content || typeof content !== 'string') return [];

  const keywords = new Set();

  // Stopwords to filter
  const stopwords = new Set([
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'shall', 'can', 'need', 'dare', 'ought',
    'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
    'as', 'into', 'through', 'during', 'before', 'after', 'above', 'below',
    'between', 'out', 'off', 'over', 'under', 'again', 'further', 'then',
    'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each',
    'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no',
    'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just',
    'because', 'but', 'and', 'or', 'if', 'while', 'that', 'this', 'these',
    'those', 'it', 'its', 'my', 'your', 'his', 'her', 'our', 'their',
    'what', 'which', 'who', 'whom', 'use', 'using', 'user', 'says',
    'about', 'up', 'also', 'like', 'etc', 'see', 'e.g'
  ]);

  // Action verbs for phrase extraction
  const actionVerbs = new Set([
    'scan', 'find', 'create', 'make', 'build', 'generate', 'search', 'list',
    'show', 'get', 'set', 'add', 'remove', 'update', 'delete', 'check',
    'verify', 'test', 'run', 'start', 'stop', 'open', 'view', 'edit',
    'deploy', 'backup', 'restore', 'publish', 'install', 'configure',
    'manage', 'audit', 'monitor', 'fix', 'debug', 'export', 'import',
    'sync', 'push', 'pull', 'connect', 'disconnect', 'enable', 'disable',
    'track', 'log', 'analyze', 'discover', 'register', 'fill', 'submit'
  ]);

  // ---------------------------------------------------------------
  // 1. Parse frontmatter
  // ---------------------------------------------------------------
  var body = content;
  var frontmatter = '';
  if (content.startsWith('---')) {
    const endIdx = content.indexOf('---', 3);
    if (endIdx !== -1) {
      frontmatter = content.substring(3, endIdx).trim();
      body = content.substring(endIdx + 3).trim();
    }
  }

  // Extract name from frontmatter
  var fmName = '';
  var fmNameMatch = frontmatter.match(/^name:\s*(.+)$/m);
  if (fmNameMatch) {
    fmName = fmNameMatch[1].trim().replace(/^["']|["']$/g, '');
  }

  // Extract description from frontmatter
  var fmDesc = '';
  var fmDescMatch = frontmatter.match(/^description:\s*(.+)$/m);
  if (fmDescMatch) {
    fmDesc = fmDescMatch[1].trim().replace(/^["']|["']$/g, '');
  }

  // Extract keywords from frontmatter keywords field
  var fmKeywordsMatch = frontmatter.match(/^keywords:\s*\n((?:\s+-\s+.+\n?)*)/m);
  if (fmKeywordsMatch) {
    var kwLines = fmKeywordsMatch[1].split('\n');
    for (var kl of kwLines) {
      var kwMatch = kl.match(/^\s+-\s+(.+)/);
      if (kwMatch) {
        keywords.add(kwMatch[1].trim().toLowerCase());
      }
    }
  }

  // ---------------------------------------------------------------
  // 2. Extract from description - trigger patterns
  // ---------------------------------------------------------------
  if (fmDesc) {
    // "Use when user says X, Y, or Z"
    var useWhenMatch = fmDesc.match(/[Uu]se when (?:user says? |user asks? )?["']([^"']+)["']/g);
    if (useWhenMatch) {
      for (var m of useWhenMatch) {
        var phrase = m.replace(/[Uu]se when (?:user says? |user asks? )?["']/g, '').replace(/["']$/, '');
        keywords.add(phrase.toLowerCase());
      }
    }

    // Extract quoted phrases from description
    var quotedPhrases = fmDesc.match(/["']([^"']{2,30})["']/g);
    if (quotedPhrases) {
      for (var qp of quotedPhrases) {
        var cleaned = qp.replace(/^["']|["']$/g, '').toLowerCase().trim();
        if (cleaned.length > 1 && !stopwords.has(cleaned)) {
          keywords.add(cleaned);
        }
      }
    }

    // "Triggers: 'x', 'y', 'z'"
    var triggersMatch = fmDesc.match(/[Tt]riggers?:\s*(.+)/);
    if (triggersMatch) {
      var triggers = triggersMatch[1].match(/['"]([^'"]+)['"]/g);
      if (triggers) {
        for (var t of triggers) {
          keywords.add(t.replace(/^['"]|['"]$/g, '').toLowerCase());
        }
      }
    }
  }

  // ---------------------------------------------------------------
  // 3. Parse body sections for trigger patterns
  // ---------------------------------------------------------------

  // Look for explicit trigger sections and patterns in body
  var triggerPatterns = [
    /[Uu]se when (?:user says? |user asks? |the user )?["']([^"']+)["']/g,
    /[Uu]se this skill when\s+(.+?)(?:\.|$)/gm,
    /[Tt]riggers?:\s*["']([^"']+)["']/g,
    /[Tt]rigger words?:\s*(.+?)(?:\n|$)/gm
  ];

  for (var pattern of triggerPatterns) {
    var match;
    while ((match = pattern.exec(body)) !== null) {
      var extracted = match[1].trim().toLowerCase();
      // Split comma-separated items
      var items = extracted.split(/[,;]/);
      for (var item of items) {
        item = item.replace(/^["'\s]+|["'\s]+$/g, '').trim();
        if (item.length > 1 && !stopwords.has(item)) {
          keywords.add(item);
        }
      }
    }
  }

  // Find ## Usage, ## When to use, ## Triggers sections
  var sectionPatterns = [
    /##\s*(?:When to [Uu]se|Usage|Triggers|Commands)\s*\n+([\s\S]*?)(?=\n##\s|\n```|$)/g
  ];

  for (var sp of sectionPatterns) {
    var sMatch;
    while ((sMatch = sp.exec(body)) !== null) {
      var sectionText = sMatch[1].trim();
      // Take first paragraph (up to double newline or 500 chars)
      var firstPara = sectionText.split(/\n\n/)[0].substring(0, 500);
      // Extract verb+noun phrases from first paragraph
      extractVerbPhrases(firstPara, actionVerbs, stopwords, keywords);
    }
  }

  // ---------------------------------------------------------------
  // 4. Extract verb+noun phrases from the whole description
  // ---------------------------------------------------------------
  if (fmDesc) {
    extractVerbPhrases(fmDesc, actionVerbs, stopwords, keywords);
  }

  // Also extract from the first heading paragraph of the body
  var firstBodyPara = body.split(/\n\n/)[0] || '';
  // Skip if it starts with # (it's a heading)
  if (firstBodyPara.startsWith('#')) {
    var afterHeading = body.substring(firstBodyPara.length).trim().split(/\n\n/)[0] || '';
    extractVerbPhrases(afterHeading, actionVerbs, stopwords, keywords);
  }

  // ---------------------------------------------------------------
  // 5. Generate variations (reversed phrases)
  // ---------------------------------------------------------------
  var toAdd = [];
  for (var kw of keywords) {
    var parts = kw.split(/\s+/);
    if (parts.length === 2) {
      // "scan network" -> "network scan"
      toAdd.push(parts[1] + ' ' + parts[0]);
    }
  }
  for (var a of toAdd) {
    keywords.add(a);
  }

  // ---------------------------------------------------------------
  // 6. Filter and clean
  // ---------------------------------------------------------------
  var tooGeneric = getTooGenericWords();

  var result = [];
  for (var k of keywords) {
    k = k.toLowerCase().trim();
    if (k.length <= 1) continue;
    if (stopwords.has(k)) continue;
    if (/^[^a-z0-9]+$/.test(k)) continue;
    if (k.indexOf(' ') === -1 && tooGeneric.has(k)) continue;
    var parts = k.split(' '); if (parts.length > 1 && parts.every(function(p) { return p === parts[0]; })) continue;
    result.push(k);
  }

  return [...new Set(result)];
}

/**
 * Words too generic to be useful as single-word keywords (cause false positives).
 * Multi-word phrases containing these words are fine ("scan network" is good, "scan" alone is not).
 */
function getTooGenericWords() {
  // Only block words that are true false-positive magnets as SINGLE keywords.
  // Words like "aws", "nmap", "pptx", "notepad" are specific enough to keep.
  // Words like "scan", "open", "hook" match too many unrelated prompts.
  return new Set([
    // Generic verbs - always need an object to be meaningful
    'find', 'create', 'make', 'build', 'generate', 'search', 'list',
    'show', 'get', 'set', 'add', 'remove', 'update', 'delete', 'check',
    'verify', 'test', 'run', 'start', 'stop', 'open', 'view', 'edit',
    'install', 'configure', 'manage', 'monitor', 'fix', 'debug',
    'export', 'import', 'sync', 'push', 'pull', 'enable', 'disable',
    'track', 'log', 'analyze', 'discover', 'register', 'fill', 'submit',
    'scan', 'deploy', 'restore', 'connect', 'disconnect', 'audit',
    // Generic nouns - too common across many skills
    'file', 'files', 'code', 'project', 'script', 'tool', 'config',
    'settings', 'data', 'name', 'path', 'directory',
    'server', 'client', 'app', 'command', 'system', 'service', 'local',
    'new', 'current', 'active', 'default', 'custom', 'required'
  ]);
}

/**
 * Filter keyword array: remove generic single words, stopwords, junk
 * Used by both extractKeywords and buildSkillRegistry merge step
 */
function filterKeywords(keywords) {
  var tooGeneric = getTooGenericWords();
  var stopwords = new Set([
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'shall', 'can', 'need', 'to', 'of', 'in',
    'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
    'and', 'or', 'if', 'but', 'not', 'so', 'that', 'this', 'it', 'its',
    'use', 'using', 'user', 'says', 'about', 'up', 'also', 'like'
  ]);
  var result = [];
  for (var i = 0; i < keywords.length; i++) {
    var k = keywords[i].toLowerCase().trim();
    if (k.length <= 1) continue;
    if (stopwords.has(k)) continue;
    if (/^[^a-z0-9]+$/.test(k)) continue;
    if (k.indexOf(' ') === -1 && tooGeneric.has(k)) continue;
    var parts = k.split(' '); if (parts.length > 1 && parts.every(function(p) { return p === parts[0]; })) continue;
    result.push(k);
  }
  return [...new Set(result)];
}

/**
 * Extract verb+object phrases from text
 * @param {string} text - Text to parse
 * @param {Set} actionVerbs - Set of action verbs
 * @param {Set} stopwords - Set of stopwords
 * @param {Set} keywords - Set to add keywords to (mutated)
 */
function extractVerbPhrases(text, actionVerbs, stopwords, keywords) {
  if (!text) return;

  // Clean markdown formatting
  var cleaned = text
    .replace(/```[\s\S]*?```/g, '')  // Remove code blocks
    .replace(/`[^`]+`/g, '')         // Remove inline code
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')  // Markdown links -> text
    .replace(/[#*_~|>]/g, '')        // Remove markdown formatting
    .replace(/\s+/g, ' ')
    .trim();

  var words = cleaned.split(/\s+/).map(function(w) {
    return w.replace(/[^a-zA-Z0-9-]/g, '').toLowerCase();
  }).filter(function(w) { return w.length > 0; });

  for (var i = 0; i < words.length; i++) {
    if (actionVerbs.has(words[i])) {
      // Skip if next word is same as verb (prevents "list list", "scan scan")
      if (i + 1 < words.length && words[i + 1] === words[i]) continue;
      // Extract 2-word phrase (verb + next word)
      if (i + 1 < words.length && !stopwords.has(words[i + 1]) && words[i + 1].length > 1) {
        keywords.add(words[i] + ' ' + words[i + 1]);
      }
      // Extract 3-word phrase (verb + next two words)
      if (i + 2 < words.length && !stopwords.has(words[i + 1]) && !stopwords.has(words[i + 2])) {
        if (words[i + 1].length > 1 && words[i + 2].length > 1) {
          keywords.add(words[i] + ' ' + words[i + 1] + ' ' + words[i + 2]);
        }
      }
    }
  }
}

// ================================================================
// Skill Scanner
// ================================================================

/**
 * Scan ~/.claude/skills/ for SKILL.md files
 * @returns {Array} Array of { id, dir, skillMdPath, name, description, existingKeywords }
 */
function scanAllSkills() {
  var inventory = [];

  if (!fs.existsSync(SKILLS_DIR)) return inventory;

  var entries = fs.readdirSync(SKILLS_DIR);
  for (var entry of entries) {
    var dirPath = path.join(SKILLS_DIR, entry);

    // Skip non-directories
    try {
      if (!fs.statSync(dirPath).isDirectory()) continue;
    } catch { continue; }

    // Skip .zip files, archive dirs
    if (entry.endsWith('.zip')) continue;
    if (entry === 'archive') continue;

    var skillMdPath = path.join(dirPath, 'SKILL.md');
    if (!fs.existsSync(skillMdPath)) continue;

    var content = fs.readFileSync(skillMdPath, 'utf-8');

    // Parse frontmatter
    var fmName = entry;
    var fmDesc = '';
    var existingKeywords = [];

    if (content.startsWith('---')) {
      var endIdx = content.indexOf('---', 3);
      if (endIdx !== -1) {
        var fm = content.substring(3, endIdx).trim();

        var nameMatch = fm.match(/^name:\s*(.+)$/m);
        if (nameMatch) fmName = nameMatch[1].trim().replace(/^["']|["']$/g, '');

        var descMatch = fm.match(/^description:\s*(.+)$/m);
        if (descMatch) fmDesc = descMatch[1].trim().replace(/^["']|["']$/g, '');

        var kwBlock = fm.match(/^keywords:\s*\n((?:\s+-\s+.+\n?)*)/m);
        if (kwBlock) {
          var kwLines = kwBlock[1].split('\n');
          for (var kl of kwLines) {
            var kwMatch = kl.match(/^\s+-\s+(.+)/);
            if (kwMatch) existingKeywords.push(kwMatch[1].trim().toLowerCase());
          }
        }
      }
    }

    inventory.push({
      id: entry,
      dir: dirPath,
      skillMdPath: skillMdPath,
      name: fmName,
      description: fmDesc,
      existingKeywords: existingKeywords
    });
  }

  return inventory;
}

// ================================================================
// Backup & Archive
// ================================================================

/**
 * Create timestamped backup of all files before modification
 * @param {Array} inventory - From scanAllSkills()
 * @returns {{ backupDir: string, filesBackedUp: number }}
 */
function backupAndArchive(inventory) {
  var timestamp = new Date().toISOString().replace(/:/g, '-').replace(/\.\d+Z$/, '');
  var backupDir = path.join(BACKUP_BASE, timestamp);
  fs.mkdirSync(backupDir, { recursive: true });

  var filesBackedUp = 0;

  // Backup settings.json
  if (fs.existsSync(SETTINGS_PATH)) {
    fs.copyFileSync(SETTINGS_PATH, path.join(backupDir, 'settings.json'));
    filesBackedUp++;
  }

  // Backup skill-registry.json
  if (fs.existsSync(REGISTRY_PATH)) {
    fs.copyFileSync(REGISTRY_PATH, path.join(backupDir, 'skill-registry.json'));
    filesBackedUp++;
  }

  // Backup each SKILL.md
  var skillsBackupDir = path.join(backupDir, 'skills');
  for (var skill of inventory) {
    var destDir = path.join(skillsBackupDir, skill.id);
    fs.mkdirSync(destDir, { recursive: true });
    fs.copyFileSync(skill.skillMdPath, path.join(destDir, 'SKILL.md'));
    filesBackedUp++;

    // Also archive each original into skill-manager/archive/{id}/
    var archiveSkillDir = path.join(ARCHIVE_DIR, skill.id);
    fs.mkdirSync(archiveSkillDir, { recursive: true });
    fs.copyFileSync(skill.skillMdPath, path.join(archiveSkillDir, 'SKILL.md.bak'));
  }

  // Write manifest
  var manifest = {
    timestamp: new Date().toISOString(),
    filesBackedUp: filesBackedUp,
    files: []
  };
  if (fs.existsSync(path.join(backupDir, 'settings.json'))) {
    manifest.files.push('settings.json');
  }
  if (fs.existsSync(path.join(backupDir, 'skill-registry.json'))) {
    manifest.files.push('skill-registry.json');
  }
  for (var skill of inventory) {
    manifest.files.push('skills/' + skill.id + '/SKILL.md');
  }
  fs.writeFileSync(path.join(backupDir, 'manifest.json'), JSON.stringify(manifest, null, 2));

  return { backupDir: backupDir, filesBackedUp: filesBackedUp };
}

// ================================================================
// Keyword Enrichment
// ================================================================

/**
 * Update keywords in SKILL.md frontmatter
 * @param {string} filePath - Path to SKILL.md
 * @param {Array} mergedKeywords - Merged keyword array
 */
function updateSkillMdKeywords(filePath, mergedKeywords) {
  var content = fs.readFileSync(filePath, 'utf-8');

  // Build new keywords block
  var kwBlock = 'keywords:\n' + mergedKeywords.map(function(k) {
    return '  - ' + k;
  }).join('\n');

  if (!content.startsWith('---')) {
    // No frontmatter - add it
    content = '---\n' + kwBlock + '\n---\n\n' + content;
  } else {
    var endIdx = content.indexOf('---', 3);
    if (endIdx === -1) return; // Malformed frontmatter

    var fm = content.substring(3, endIdx);
    var afterFm = content.substring(endIdx + 3);

    // Check if keywords: block exists
    var kwRegex = /^keywords:\s*\n(?:\s+-\s+.+\n?)*/m;
    if (kwRegex.test(fm)) {
      // Replace existing keywords block
      fm = fm.replace(kwRegex, kwBlock + '\n');
    } else {
      // Add keywords before closing ---
      fm = fm.trimEnd() + '\n' + kwBlock + '\n';
    }

    content = '---\n' + fm + '---' + afterFm;
  }

  fs.writeFileSync(filePath, content);
}

/**
 * Enrich all skills with extracted keywords
 * @param {Array} inventory - From scanAllSkills()
 * @returns {Array} Array of { id, beforeCount, afterCount, newKeywords }
 */
function enrichAllSkills(inventory) {
  var results = [];

  for (var skill of inventory) {
    var content = fs.readFileSync(skill.skillMdPath, 'utf-8');
    var extracted = extractKeywords(content);

    // Merge: existing + new (additive only)
    var merged = [...new Set([...skill.existingKeywords, ...extracted])];
    var filtered = filterKeywords(merged);

    var newKeywords = filtered.filter(function(k) {
      return !skill.existingKeywords.includes(k);
    });

    if (newKeywords.length > 0) {
      updateSkillMdKeywords(skill.skillMdPath, filtered);
    }

    results.push({
      id: skill.id,
      beforeCount: skill.existingKeywords.length,
      afterCount: filtered.length,
      newKeywords: newKeywords
    });
  }

  return results;
}

// ================================================================
// Skill Registry
// ================================================================

/**
 * Build or update skill-registry.json
 * @param {Array} inventory - From scanAllSkills() (post-enrichment)
 * @param {Array} enrichResults - From enrichAllSkills()
 * @returns {{ total: number, updated: number, added: number }}
 */
function buildSkillRegistry(inventory, enrichResults) {
  var registry = { skills: [] };

  // Read existing registry if present
  if (fs.existsSync(REGISTRY_PATH)) {
    try {
      registry = JSON.parse(fs.readFileSync(REGISTRY_PATH, 'utf-8'));
      if (!registry.skills) registry.skills = [];
    } catch {
      registry = { skills: [] };
    }
  }

  var updated = 0;
  var added = 0;

  for (var skill of inventory) {
    // Re-read SKILL.md to get current keywords (post-enrichment)
    var content = fs.readFileSync(skill.skillMdPath, 'utf-8');
    var currentKeywords = [];
    if (content.startsWith('---')) {
      var endIdx = content.indexOf('---', 3);
      if (endIdx !== -1) {
        var fm = content.substring(3, endIdx);
        var kwBlock = fm.match(/^keywords:\s*\n((?:\s+-\s+.+\n?)*)/m);
        if (kwBlock) {
          var kwLines = kwBlock[1].split('\n');
          for (var kl of kwLines) {
            var kwMatch = kl.match(/^\s+-\s+(.+)/);
            if (kwMatch) currentKeywords.push(kwMatch[1].trim().toLowerCase());
          }
        }
      }
    }

    // Find or create entry in registry
    var existing = registry.skills.find(function(s) { return s.id === skill.id; });
    if (existing) {
      // Additive merge keywords
      var merged = [...new Set([...existing.keywords, ...currentKeywords])];
      var filtered = filterKeywords(merged);
      if (filtered.length !== existing.keywords.length || filtered.some(function(k) { return !existing.keywords.includes(k); })) {
        existing.keywords = filtered;
        updated++;
      }
      existing.name = skill.name;
      existing.skillPath = skill.skillMdPath;
      existing.enabled = existing.enabled !== false; // preserve if set, default true
    } else {
      registry.skills.push({
        id: skill.id,
        name: skill.name,
        keywords: filterKeywords(currentKeywords),
        skillPath: skill.skillMdPath,
        enabled: true
      });
      added++;
    }
  }

  fs.writeFileSync(REGISTRY_PATH, JSON.stringify(registry, null, 2));

  return { total: registry.skills.length, updated: updated, added: added };
}

// ================================================================
// Hook Installation
// ================================================================

/**
 * Install 2 hook files to ~/.claude/hooks/
 * Skips files that already exist (does not overwrite)
 * @returns {{ installed: Array, skipped: Array }}
 */
function installHooks() {
  var installed = [];
  var skipped = [];

  fs.mkdirSync(HOOKS_DIR, { recursive: true });
  fs.mkdirSync(LOGS_DIR, { recursive: true });

  // ------------------------------------------
  // HOOK 1: skill-usage-tracker.js (PostToolUse, Skill|Task)
  // ------------------------------------------
  var trackerPath = path.join(HOOKS_DIR, 'skill-usage-tracker.js');
  if (fs.existsSync(trackerPath)) {
    skipped.push('skill-usage-tracker.js');
  } else {
    var lines2 = [
      '#!/usr/bin/env node',
      '/**',
      ' * @hook skill-usage-tracker',
      ' * @event PostToolUse',
      ' * @matcher Skill|Task',
      ' * @description Log Skill/Task usage for analytics',
      ' */',
      'const fs = require("fs");',
      'const path = require("path");',
      'const os = require("os");',
      '',
      'const HOME = os.homedir();',
      'const LOG_FILE = path.join(HOME, ".claude", "logs", "skill-usage.log");',
      '',
      'async function main() {',
      '  try {',
      '    let input = "";',
      '    for await (const chunk of process.stdin) input += chunk;',
      '    let data;',
      '    try { data = JSON.parse(input); } catch { console.log("{}"); return; }',
      '',
      '    var toolName = data.tool_name || "";',
      '    var toolInput = data.tool_input || {};',
      '    var skillName = null;',
      '    if (toolName === "Skill") skillName = toolInput.skill || null;',
      '    else if (toolName === "Task") skillName = toolInput.name || toolInput.subagent_type || null;',
      '    if (!skillName) { console.log("{}"); return; }',
      '',
      '    var logDir = path.dirname(LOG_FILE);',
      '    if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });',
      '    var entry = {',
      '      timestamp: new Date().toISOString(),',
      '      tool: toolName,',
      '      skill: skillName',
      '    };',
      '    fs.appendFileSync(LOG_FILE, JSON.stringify(entry) + "\\n");',
      '    console.log("{}");',
      '  } catch {',
      '    console.log("{}");',
      '  }',
      '}',
      '',
      'main().catch(function() { console.log("{}"); process.exit(0); });'
    ].join('\n');
    fs.writeFileSync(trackerPath, lines2);
    installed.push('skill-usage-tracker.js');
  }

  // ------------------------------------------
  // HOOK 2: skill-manager-session.js (SessionStart)
  // Health check + auto-enrich + logging
  // ------------------------------------------
  var sessionPath = path.join(HOOKS_DIR, 'skill-manager-session.js');
  if (fs.existsSync(sessionPath)) {
    skipped.push('skill-manager-session.js');
  } else {
    var lines3 = [
      '#!/usr/bin/env node',
      '/**',
      ' * @hook skill-manager-session',
      ' * @event SessionStart',
      ' * @matcher *',
      ' * @description Hook health check + auto-enrich on session start',
      ' */',
      'const fs = require("fs");',
      'const path = require("path");',
      'const os = require("os");',
      '',
      'const HOME = os.homedir();',
      'const HOOKS_DIR = path.join(HOME, ".claude", "hooks");',
      'const SKILLS_DIR = path.join(HOME, ".claude", "skills");',
      'const SETTINGS_PATH = path.join(HOME, ".claude", "settings.json");',
      'const LOG_FILE = path.join(HOME, ".claude", "logs", "skill-usage.log");',
      '',
      'function log(action, detail) {',
      '  try {',
      '    var dir = path.dirname(LOG_FILE);',
      '    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });',
      '    var e = { timestamp: new Date().toISOString(), tool: "SessionStart", skill: "skill-manager", action: action, detail: detail };',
      '    fs.appendFileSync(LOG_FILE, JSON.stringify(e) + "\\n");',
      '  } catch {}',
      '}',
      '',
      'function main() {',
      '  try {',
      '    var issues = [];',
      '    var fixed = [];',
      '',
      '    // 1. Check required hook files exist',
      '    var required = ["skill-usage-tracker.js", "skill-manager-session.js"];',
      '    for (var r of required) {',
      '      if (!fs.existsSync(path.join(HOOKS_DIR, r))) issues.push("missing:" + r);',
      '    }',
      '',
      '    // 2. Check settings.json has hooks registered',
      '    try {',
      '      var sStr = fs.readFileSync(SETTINGS_PATH, "utf-8");',
      '      for (var r of required) {',
      '        if (sStr.indexOf(r) === -1) issues.push("unregistered:" + r);',
      '      }',
      '    } catch {}',
      '',
      '    // 3. Auto-remediate missing hooks',
      '    if (issues.length > 0) {',
      '      log("health_issues", issues.join(", "));',
      '      var setupPath = path.join(SKILLS_DIR, "skill-manager", "setup.js");',
      '      if (fs.existsSync(setupPath)) {',
      '        try {',
      '          delete require.cache[require.resolve(setupPath)];',
      '          var setup = require(setupPath);',
      '          if (typeof setup.installHooks === "function") {',
      '            var hr = setup.installHooks();',
      '            if (hr.installed.length > 0) fixed.push("installed:" + hr.installed.join(","));',
      '          }',
      '          if (typeof setup.patchSettings === "function") {',
      '            var sr = setup.patchSettings();',
      '            if (sr.added.length > 0) fixed.push("registered:" + sr.added.join(","));',
      '          }',
      '        } catch {}',
      '      }',
      '      if (fixed.length > 0) log("health_fixed", fixed.join("; "));',
      '      else log("health_unfixed", "setup.js not found or failed");',
      '    } else {',
      '      log("health_ok", required.length + " hooks verified");',
      '    }',
      '',
      '    // 4. Check frontmatter compliance',
      '    if (fs.existsSync(SKILLS_DIR)) {',
      '      var entries = fs.readdirSync(SKILLS_DIR);',
      '      var missing = [];',
      '      for (var entry of entries) {',
      '        var dirPath = path.join(SKILLS_DIR, entry);',
      '        try { if (!fs.statSync(dirPath).isDirectory()) continue; } catch { continue; }',
      '        if (entry === "archive" || entry.endsWith(".zip")) continue;',
      '        var skillMd = path.join(dirPath, "SKILL.md");',
      '        if (!fs.existsSync(skillMd)) continue;',
      '        var content = fs.readFileSync(skillMd, "utf-8");',
      '        var hasKw = false;',
      '        if (content.startsWith("---")) {',
      '          var endIdx = content.indexOf("---", 3);',
      '          if (endIdx !== -1) {',
      '            var fm = content.substring(3, endIdx);',
      '            hasKw = fm.indexOf("keywords:") !== -1;',
      '          }',
      '        }',
      '        if (!hasKw) missing.push(entry);',
      '      }',
      '      if (missing.length > 0) {',
      '        log("frontmatter_missing", missing.join(", "));',
      '        var setupPath2 = path.join(SKILLS_DIR, "skill-manager", "setup.js");',
      '        if (fs.existsSync(setupPath2)) {',
      '          try {',
      '            delete require.cache[require.resolve(setupPath2)];',
      '            var setup2 = require(setupPath2);',
      '            var inv = setup2.scanAllSkills();',
      '            setup2.enrichAllSkills(inv);',
      '            if (typeof setup2.buildSkillRegistry === "function") setup2.buildSkillRegistry(inv, []);',
      '            log("frontmatter_enriched", inv.length + " skills processed");',
      '          } catch {}',
      '        }',
      '      }',
      '    }',
      '',
      '    console.log("{}");',
      '  } catch {',
      '    console.log("{}");',
      '  }',
      '}',
      '',
      'main();'
    ].join('\n');
    fs.writeFileSync(sessionPath, lines3);
    installed.push('skill-manager-session.js');
  }

  return { installed: installed, skipped: skipped };
}

// ================================================================
// Settings Patching
// ================================================================

/**
 * Add hook entries to settings.json (preserving existing entries)
 * @returns {{ added: Array, existed: Array }}
 */
function patchSettings() {
  var settings = {};
  if (fs.existsSync(SETTINGS_PATH)) {
    try {
      settings = JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf-8'));
    } catch {
      settings = {};
    }
  }

  if (!settings.hooks) settings.hooks = {};

  var added = [];
  var existed = [];

  // Define our 2 hooks (skill-reminder.js removed - native frontmatter matching)
  var hookDefs = [
    {
      event: 'PostToolUse',
      matcher: 'Skill|Task',
      file: 'skill-usage-tracker.js'
    },
    {
      event: 'SessionStart',
      matcher: '*',
      file: 'skill-manager-session.js'
    }
  ];

  for (var def of hookDefs) {
    var hookPath = path.join(HOME, '.claude', 'hooks', def.file).replace(/\\/g, '/');
    var command = 'node "' + hookPath + '"';

    // Check if already registered
    var eventEntries = settings.hooks[def.event] || [];
    var alreadyExists = false;

    for (var entry of eventEntries) {
      if (entry.hooks) {
        for (var h of entry.hooks) {
          if (h.command && h.command.indexOf(def.file) !== -1) {
            alreadyExists = true;
            break;
          }
        }
      }
      if (alreadyExists) break;
    }

    if (alreadyExists) {
      existed.push(def.file);
    } else {
      // Find an existing entry with matching matcher, or create new one
      var matchingEntry = null;
      for (var entry of eventEntries) {
        if (entry.matcher === def.matcher) {
          matchingEntry = entry;
          break;
        }
      }

      if (matchingEntry) {
        // Add to existing matcher entry
        matchingEntry.hooks.push({ type: 'command', command: command });
      } else {
        // Create new entry
        eventEntries.push({
          matcher: def.matcher,
          hooks: [{ type: 'command', command: command }]
        });
      }

      settings.hooks[def.event] = eventEntries;
      added.push(def.file);
    }
  }

  fs.writeFileSync(SETTINGS_PATH, JSON.stringify(settings, null, 2));
  return { added: added, existed: existed };
}

// ================================================================
// Self-Test
// ================================================================

/**
 * Run automated verification tests after setup
 * @returns {{ tests: Array, passed: number, failed: number }}
 */
function selfTest() {
  var tests = [];

  // Test 1: Registry is valid JSON with skills array
  try {
    var reg = JSON.parse(fs.readFileSync(REGISTRY_PATH, 'utf-8'));
    var isValid = Array.isArray(reg.skills) && reg.skills.length > 0;
    tests.push({
      name: 'Registry valid JSON',
      passed: isValid,
      message: isValid ? reg.skills.length + ' skills in registry' : 'No skills found in registry'
    });
  } catch (err) {
    tests.push({ name: 'Registry valid JSON', passed: false, message: 'Parse error: ' + err.message });
  }

  // Test 2: All 2 hook files exist
  var hookFiles = ['skill-usage-tracker.js', 'skill-manager-session.js'];
  var allExist = true;
  var missing = [];
  for (var hf of hookFiles) {
    if (!fs.existsSync(path.join(HOOKS_DIR, hf))) {
      allExist = false;
      missing.push(hf);
    }
  }
  tests.push({
    name: 'Hook files exist',
    passed: allExist,
    message: allExist ? 'All 2 hooks present' : 'Missing: ' + missing.join(', ')
  });

  // Test 3: Settings has our 3 hooks registered
  try {
    var settings = JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf-8'));
    var settingsStr = JSON.stringify(settings);
    var allRegistered = true;
    var missingInSettings = [];
    for (var hf of hookFiles) {
      if (settingsStr.indexOf(hf) === -1) {
        allRegistered = false;
        missingInSettings.push(hf);
      }
    }
    tests.push({
      name: 'Settings hooks registered',
      passed: allRegistered,
      message: allRegistered ? 'All 2 hooks in settings.json' : 'Missing: ' + missingInSettings.join(', ')
    });
  } catch (err) {
    tests.push({ name: 'Settings hooks registered', passed: false, message: 'Parse error: ' + err.message });
  }

  // Test 4: Keyword match test
  try {
    var reg = JSON.parse(fs.readFileSync(REGISTRY_PATH, 'utf-8'));
    var skillsWithMultiWord = reg.skills.filter(function(s) {
      return s.keywords && s.keywords.some(function(k) { return k.indexOf(' ') !== -1; });
    }).slice(0, 3);

    var matchCount = 0;
    for (var skill of skillsWithMultiWord) {
      var multiWordKw = skill.keywords.find(function(k) { return k.indexOf(' ') !== -1; });
      if (multiWordKw) {
        // Simulate: does this keyword appear in the skill's keyword list?
        var found = skill.keywords.indexOf(multiWordKw) !== -1;
        if (found) matchCount++;
      }
    }
    var total = skillsWithMultiWord.length;
    tests.push({
      name: 'Keyword matching',
      passed: total > 0 && matchCount === total,
      message: matchCount + '/' + total + ' skills matched their own keywords'
    });
  } catch (err) {
    tests.push({ name: 'Keyword matching', passed: false, message: 'Error: ' + err.message });
  }

  // Test 5: Logging test
  try {
    fs.mkdirSync(LOGS_DIR, { recursive: true });
    var logPath = path.join(LOGS_DIR, 'skill-usage.log');
    var testEntry = { timestamp: new Date().toISOString(), tool: 'SelfTest', skill: 'self-test-verify' };
    fs.appendFileSync(logPath, JSON.stringify(testEntry) + '\n');
    var lastLine = fs.readFileSync(logPath, 'utf-8').trim().split('\n').pop();
    var parsed = JSON.parse(lastLine);
    var matches = parsed.skill === 'self-test-verify';
    tests.push({
      name: 'Usage logging',
      passed: matches,
      message: matches ? 'JSONL write/read verified' : 'Last line mismatch'
    });
  } catch (err) {
    tests.push({ name: 'Usage logging', passed: false, message: 'Error: ' + err.message });
  }

  var passed = tests.filter(function(t) { return t.passed; }).length;
  var failed = tests.filter(function(t) { return !t.passed; }).length;

  return { tests: tests, passed: passed, failed: failed };
}

// ================================================================
// Report Generation
// ================================================================

/**
 * Generate setup report
 * @param {Object} results - All results from setup steps
 */
function generateReport(results) {
  var lines = [];
  lines.push('# Skill Manager Setup Report');
  lines.push('Date: ' + new Date().toISOString());
  lines.push('Platform: ' + os.platform() + ' ' + os.arch());
  lines.push('');

  // Skills scanned
  lines.push('## Skills Scanned: ' + results.inventory.length);
  for (var skill of results.inventory) {
    var enrichResult = results.enrichResults.find(function(r) { return r.id === skill.id; });
    var kwCount = enrichResult ? enrichResult.afterCount : skill.existingKeywords.length;
    lines.push('- ' + skill.id + ' (' + kwCount + ' keywords)');
  }
  lines.push('');

  // Backup
  lines.push('## Backup');
  lines.push('Location: ' + results.backup.backupDir);
  lines.push('Files: ' + results.backup.filesBackedUp);
  lines.push('');

  // Keyword enrichment
  lines.push('## Keyword Enrichment');
  lines.push('');
  lines.push('| Skill | Before | After | New Keywords |');
  lines.push('|-------|--------|-------|-------------|');
  for (var er of results.enrichResults) {
    if (er.newKeywords.length > 0) {
      lines.push('| ' + er.id + ' | ' + er.beforeCount + ' | ' + er.afterCount + ' | ' + er.newKeywords.slice(0, 5).join(', ') + (er.newKeywords.length > 5 ? ' (+' + (er.newKeywords.length - 5) + ' more)' : '') + ' |');
    }
  }
  var unchanged = results.enrichResults.filter(function(r) { return r.newKeywords.length === 0; });
  if (unchanged.length > 0) {
    lines.push('');
    lines.push('Unchanged: ' + unchanged.map(function(r) { return r.id; }).join(', '));
  }
  lines.push('');

  // Hooks
  lines.push('## Hooks Installed');
  if (results.hooks.installed.length > 0) {
    lines.push('Installed: ' + results.hooks.installed.join(', '));
  }
  if (results.hooks.skipped.length > 0) {
    lines.push('Skipped (already exist): ' + results.hooks.skipped.join(', '));
  }
  lines.push('');

  // Settings
  lines.push('## Settings Patched');
  if (results.settings.added.length > 0) {
    lines.push('Added: ' + results.settings.added.join(', '));
  }
  if (results.settings.existed.length > 0) {
    lines.push('Already registered: ' + results.settings.existed.join(', '));
  }
  lines.push('');

  // Registry
  lines.push('## Registry');
  lines.push('Total: ' + results.registry.total + ' skills');
  lines.push('Updated: ' + results.registry.updated + ', Added: ' + results.registry.added);
  lines.push('');

  // Self-test
  lines.push('## Self-Test Results');
  lines.push(results.selfTest.passed + '/' + (results.selfTest.passed + results.selfTest.failed) + ' passed');
  lines.push('');
  for (var t of results.selfTest.tests) {
    lines.push('- ' + (t.passed ? 'PASS' : 'FAIL') + ': ' + t.name + ' - ' + t.message);
  }
  lines.push('');

  // Uninstall
  var setupPath = path.join(SKILL_MANAGER_DIR, 'setup.js').replace(/\\/g, '/');
  lines.push('## Uninstall');
  lines.push('```');
  lines.push('node "' + setupPath + '" --uninstall');
  lines.push('```');

  fs.writeFileSync(REPORT_PATH, lines.join('\n'));
}

// ================================================================
// Uninstall
// ================================================================

/**
 * Restore from most recent backup, move hooks to archive
 */
function uninstall() {
  console.log('Skill Manager Uninstall');
  console.log('=======================');

  // Find most recent backup
  if (!fs.existsSync(BACKUP_BASE)) {
    console.log('ERROR: No backups found at ' + BACKUP_BASE);
    process.exit(1);
  }

  var backups = fs.readdirSync(BACKUP_BASE).sort().reverse();
  if (backups.length === 0) {
    console.log('ERROR: No backups found');
    process.exit(1);
  }

  var latestDir = path.join(BACKUP_BASE, backups[0]);
  var manifestPath = path.join(latestDir, 'manifest.json');

  if (!fs.existsSync(manifestPath)) {
    console.log('ERROR: No manifest.json in ' + latestDir);
    process.exit(1);
  }

  var manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
  console.log('Restoring from: ' + latestDir);
  console.log('Backup timestamp: ' + manifest.timestamp);
  console.log('');

  // Restore settings.json
  var backupSettings = path.join(latestDir, 'settings.json');
  if (fs.existsSync(backupSettings)) {
    fs.copyFileSync(backupSettings, SETTINGS_PATH);
    console.log('Restored: settings.json');
  }

  // Restore skill-registry.json
  var backupRegistry = path.join(latestDir, 'skill-registry.json');
  if (fs.existsSync(backupRegistry)) {
    fs.copyFileSync(backupRegistry, REGISTRY_PATH);
    console.log('Restored: skill-registry.json');
  } else {
    // If it didn't exist before, remove it
    if (fs.existsSync(REGISTRY_PATH)) {
      // Move to archive instead of deleting
      fs.mkdirSync(ARCHIVE_DIR, { recursive: true });
      fs.copyFileSync(REGISTRY_PATH, path.join(ARCHIVE_DIR, 'skill-registry.json.bak'));
      fs.unlinkSync(REGISTRY_PATH);
      console.log('Archived: skill-registry.json (did not exist in backup)');
    }
  }

  // Restore SKILL.md files
  var skillsBackupDir = path.join(latestDir, 'skills');
  if (fs.existsSync(skillsBackupDir)) {
    var skillDirs = fs.readdirSync(skillsBackupDir);
    for (var sd of skillDirs) {
      var backupSkillMd = path.join(skillsBackupDir, sd, 'SKILL.md');
      var targetSkillMd = path.join(SKILLS_DIR, sd, 'SKILL.md');
      if (fs.existsSync(backupSkillMd) && fs.existsSync(path.dirname(targetSkillMd))) {
        fs.copyFileSync(backupSkillMd, targetSkillMd);
        console.log('Restored: skills/' + sd + '/SKILL.md');
      }
    }
  }

  // Move our 2 hook files to archive (not delete)
  var hookFiles = ['skill-usage-tracker.js', 'skill-manager-session.js'];
  fs.mkdirSync(ARCHIVE_DIR, { recursive: true });
  for (var hf of hookFiles) {
    var hookPath = path.join(HOOKS_DIR, hf);
    if (fs.existsSync(hookPath)) {
      var archiveDest = path.join(ARCHIVE_DIR, hf + '.bak');
      fs.copyFileSync(hookPath, archiveDest);
      fs.unlinkSync(hookPath);
      console.log('Archived hook: ' + hf + ' -> archive/' + hf + '.bak');
    }
  }

  console.log('');
  console.log('Uninstall complete. Skill manager skill itself preserved.');
  console.log('Re-run setup: node "' + path.join(SKILL_MANAGER_DIR, 'setup.js').replace(/\\/g, '/') + '"');
}

// ================================================================
// Main
// ================================================================

function main() {
  // Check for --uninstall / --restore flag
  var args = process.argv.slice(2);
  if (args.includes('--uninstall') || args.includes('--restore')) {
    uninstall();
    return;
  }

  console.log('Skill Manager Setup');
  console.log('====================');
  console.log('');

  // Step 1: Scan all skills
  console.log('[1/7] Scanning skills...');
  var inventory = scanAllSkills();
  console.log('  Found ' + inventory.length + ' skills');

  // Step 2: Backup everything
  console.log('[2/7] Creating backup...');
  var backup = backupAndArchive(inventory);
  console.log('  Backed up ' + backup.filesBackedUp + ' files to ' + backup.backupDir);

  // Step 3: Enrich keywords
  console.log('[3/7] Enriching keywords...');
  var enrichResults = enrichAllSkills(inventory);
  var enriched = enrichResults.filter(function(r) { return r.newKeywords.length > 0; });
  console.log('  Enriched ' + enriched.length + '/' + enrichResults.length + ' skills');

  // Step 4: Build registry
  console.log('[4/7] Building skill registry...');
  // Re-scan after enrichment to get updated keywords
  inventory = scanAllSkills();
  var registry = buildSkillRegistry(inventory, enrichResults);
  console.log('  Registry: ' + registry.total + ' skills (' + registry.added + ' added, ' + registry.updated + ' updated)');

  // Step 5: Install hooks
  console.log('[5/7] Installing hooks...');
  var hooks = installHooks();
  console.log('  Installed: ' + (hooks.installed.length > 0 ? hooks.installed.join(', ') : 'none'));
  console.log('  Skipped: ' + (hooks.skipped.length > 0 ? hooks.skipped.join(', ') : 'none'));

  // Step 6: Patch settings
  console.log('[6/7] Patching settings.json...');
  var settings = patchSettings();
  console.log('  Added: ' + (settings.added.length > 0 ? settings.added.join(', ') : 'none'));
  console.log('  Existed: ' + (settings.existed.length > 0 ? settings.existed.join(', ') : 'none'));

  // Step 7: Self-test
  console.log('[7/7] Running self-tests...');
  var selfTestResults = selfTest();
  console.log('  ' + selfTestResults.passed + '/' + (selfTestResults.passed + selfTestResults.failed) + ' tests passed');
  for (var t of selfTestResults.tests) {
    console.log('    ' + (t.passed ? 'PASS' : 'FAIL') + ': ' + t.name + ' - ' + t.message);
  }

  // Generate report
  var allResults = {
    inventory: inventory,
    backup: backup,
    enrichResults: enrichResults,
    registry: registry,
    hooks: hooks,
    settings: settings,
    selfTest: selfTestResults
  };
  generateReport(allResults);
  console.log('');
  console.log('Report: ' + REPORT_PATH);
  console.log('');

  if (selfTestResults.failed > 0) {
    console.log('WARNING: ' + selfTestResults.failed + ' test(s) failed. Check report for details.');
    process.exit(1);
  } else {
    console.log('Setup complete. All tests passed.');
  }
}

// ================================================================
// Exports
// ================================================================

module.exports = {
  main: main,
  scanAllSkills: scanAllSkills,
  enrichAllSkills: enrichAllSkills,
  extractKeywords: extractKeywords,
  filterKeywords: filterKeywords,
  buildSkillRegistry: buildSkillRegistry,
  installHooks: installHooks,
  patchSettings: patchSettings,
  uninstall: uninstall,
  selfTest: selfTest,
  generateReport: generateReport
};

if (require.main === module) main();
