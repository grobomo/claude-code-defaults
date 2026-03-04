#!/usr/bin/env node
/**
 * @hook gsd-intel-prune
 * @event Stop
 * @matcher *
 * @description Cleans up stale entries from the codebase intelligence index on
 *   session stop. Reads .planning/intel/index.json and removes entries for files
 *   that no longer exist on disk. This prevents the index from growing stale when
 *   files are deleted or renamed. Runs silently and only logs when entries are
 *   actually pruned.
 */
const log = require('./hook-logger');
const HOOK_NAME = 'gsd-intel-prune';
const EVENT_TYPE = 'Stop';

const fs = require('fs');
const path = require('path');

function pruneIndex() {
  const intelDir = path.join(process.cwd(), '.planning', 'intel');
  const indexPath = path.join(intelDir, 'index.json');

  if (!fs.existsSync(intelDir)) {
    return { pruned: 0, total: 0 };
  }

  let index;
  try {
    index = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
  } catch (e) {
    return { pruned: 0, total: 0 };
  }

  if (!index.files || typeof index.files !== 'object') {
    return { pruned: 0, total: 0 };
  }

  const filePaths = Object.keys(index.files);
  const deleted = filePaths.filter(fp => !fs.existsSync(fp));

  if (deleted.length === 0) {
    return { pruned: 0, total: filePaths.length };
  }

  for (const fp of deleted) {
    delete index.files[fp];
  }
  index.updated = Date.now();
  fs.writeFileSync(indexPath, JSON.stringify(index, null, 2));

  return { pruned: deleted.length, total: filePaths.length };
}

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
  try {
    const result = pruneIndex();
    if (result.pruned > 0) {
      log(HOOK_NAME, EVENT_TYPE, `pruned ${result.pruned}/${result.total} stale entries`);
    } else {
      log(HOOK_NAME, EVENT_TYPE, 'no stale entries');
    }
    process.exit(0);
  } catch (error) {
    log(HOOK_NAME, EVENT_TYPE, `error: ${error.message}`, 'ERROR');
    process.exit(0);
  }
});
