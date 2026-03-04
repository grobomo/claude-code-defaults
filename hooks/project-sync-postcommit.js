#!/usr/bin/env node
/**
 * @hook project-sync-postcommit
 * @event PostToolUse
 * @matcher Bash
 * @description Detects git commits that modify documentation and suggests wiki sync.
 *   After any Bash command containing "git commit", checks the committed files for
 *   documentation patterns (README.md, CLAUDE.md, WIKI.md, docs/, wiki-pages/).
 *   If doc files changed, outputs a hint suggesting the user sync to their wiki.
 *   Works with the project-sync skill for automated documentation publishing.
 */
const fs = require('fs');
const { execSync } = require('child_process');
const log = require('./hook-logger');
const HOOK_NAME = 'project-sync-postcommit';
const EVENT_TYPE = 'PostToolUse';

let input = '';
try { input = fs.readFileSync(0, 'utf-8'); } catch (e) { process.exit(0); }

let data;
try { data = JSON.parse(input); } catch (e) { process.exit(0); }

if (data.tool_name !== 'Bash' || data.tool_result?.exit_code !== 0) {
  process.exit(0);
}

const command = data.tool_input?.command || '';
if (!command.includes('git commit')) {
  process.exit(0);
}

log(HOOK_NAME, EVENT_TYPE, 'git commit detected');

const docPatterns = /README\.md|CLAUDE\.md|WIKI\.md|wiki-pages\/.*\.md|docs\/.*\.md/;
try {
  const changed = execSync('git diff --name-only HEAD~1 HEAD', { encoding: 'utf-8', timeout: 5000, stdio: ['pipe', 'pipe', 'pipe'] });
  const docFiles = changed.split('\n').filter(f => docPatterns.test(f));
  if (docFiles.length > 0) {
    log(HOOK_NAME, EVENT_TYPE, `docs changed: ${docFiles.join(', ')}`);
    console.log('<project-sync-hint>');
    console.log('Doc files changed in commit. Wiki sync recommended.');
    console.log('Changed: ' + docFiles.join(', '));
    console.log('</project-sync-hint>');
  } else {
    log(HOOK_NAME, EVENT_TYPE, 'commit had no doc changes');
  }
} catch (e) {
  log(HOOK_NAME, EVENT_TYPE, 'git diff failed (not in repo?)');
}
process.exit(0);
