#!/usr/bin/env node
/**
 * Hook Report Generator - parses frontmatter and generates report
 */
const fs = require('fs');
const path = require('path');
const os = require('os');

const homeDir = os.homedir();
const settingsPath = path.join(homeDir, '.claude', 'settings.json');
const reportPath = path.join(homeDir, '.claude', 'hooks', 'HOOKS-REPORT.md');

function parseDescription(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    
    // JS: /** ... @description text ... */
    const jsMatch = content.match(/@description\s+([\s\S]*?)(?:\n\s*\*\/|\n\s*\*\s*@)/);
    if (jsMatch) {
      return jsMatch[1].replace(/^\s*\*\s?/gm, '').replace(/\s+/g, ' ').trim();
    }
    
    // Shell/Python: # @description text
    const shellMatch = content.match(/#\s*@description\s+(.+?)(?:\n[^#]|\n#\s*@|$)/s);
    if (shellMatch) {
      return shellMatch[1].replace(/\n#\s*/g, ' ').replace(/\s+/g, ' ').trim();
    }
    
    // Python docstring
    const pyMatch = content.match(/@description\s+([\s\S]*?)(?:\n\s*@|""")/);
    if (pyMatch) {
      return pyMatch[1].replace(/\s+/g, ' ').trim();
    }
    
    return null;
  } catch (e) { return null; }
}

function resolvePath(cmd) {
  const m = cmd.match(/(?:node|python|bash)\s+"([^"]+)"|"([^"]+\.(?:js|py|sh))"/);
  if (m) {
    let fp = (m[1] || m[2]).replace(/\$HOME/g, homeDir);
    return path.normalize(fp);
  }
  return null;
}

const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));

const events = ['SessionStart', 'UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'PreCompact', 'SessionEnd', 'Stop'];
const when = {
  SessionStart: 'When Claude Code starts a new session',
  UserPromptSubmit: 'After user sends a message, before Claude processes',
  PreToolUse: 'Before Claude executes any tool',
  PostToolUse: 'After Claude executes any tool',
  PreCompact: 'Before context is compacted (summarized)',
  SessionEnd: 'When session ends normally',
  Stop: 'When session is stopped/interrupted'
};

const out = [];
const date = new Date().toISOString().split('T')[0];
out.push('# Claude Code Hooks Report', 'Generated: ' + date, '', 'All configured hooks with descriptions.', '');

for (const ev of events) {
  const groups = settings.hooks?.[ev] || [];
  if (!groups.length) continue;
  
  out.push('## ' + ev, '**When:** ' + when[ev], '');
  
  for (const g of groups) {
    out.push('### Matcher: `' + (g.matcher || '*') + '`', '');
    for (const h of g.hooks || []) {
      const fp = resolvePath(h.command || '');
      const name = fp ? path.basename(fp) : (h.command || '').split(path.sep).pop();
      const async = h.async ? ' *(async)*' : '';
      const desc = fp ? parseDescription(fp) : null;
      out.push('#### ' + name + async, desc || '*No description*', '');
    }
  }
  out.push('---', '');
}

if (settings.statusLine?.command) {
  out.push('## Statusline', '**When:** Continuously', '');
  const fp = resolvePath(settings.statusLine.command);
  const name = fp ? path.basename(fp) : 'statusline';
  const desc = fp ? parseDescription(fp) : null;
  out.push('#### ' + name, desc || '*No description*', '');
}

fs.writeFileSync(reportPath, out.join('\n'));

// Console output
console.log('='.repeat(60));
console.log('           CLAUDE CODE HOOKS REPORT - ' + date);
console.log('='.repeat(60), '');

for (const ev of events) {
  const groups = settings.hooks?.[ev] || [];
  if (!groups.length) continue;
  console.log('-'.repeat(60));
  console.log('EVENT: ' + ev + ' | ' + when[ev]);
  console.log('-'.repeat(60));
  for (const g of groups) {
    console.log('  [' + (g.matcher || '*') + ']');
    for (const h of g.hooks || []) {
      const fp = resolvePath(h.command || '');
      const name = fp ? path.basename(fp) : (h.command || '').split(path.sep).pop();
      const async = h.async ? ' (async)' : '';
      const desc = fp ? parseDescription(fp) : null;
      console.log('    ' + name + async);
      if (desc) console.log('      ' + (desc.length > 90 ? desc.slice(0,90) + '...' : desc));
    }
  }
  console.log('');
}

if (settings.statusLine?.command) {
  console.log('-'.repeat(60));
  console.log('STATUSLINE');
  console.log('-'.repeat(60));
  const fp = resolvePath(settings.statusLine.command);
  const name = fp ? path.basename(fp) : 'statusline';
  const desc = fp ? parseDescription(fp) : null;
  console.log('    ' + name);
  if (desc) console.log('      ' + (desc.length > 90 ? desc.slice(0,90) + '...' : desc));
  console.log('');
}

console.log('Saved: ' + reportPath);
