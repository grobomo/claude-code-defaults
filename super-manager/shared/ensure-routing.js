#!/usr/bin/env node
/**
 * CLI wrapper for ensureRoutingInstruction().
 * Callable from any language (Python, Bash, Node) during setup.
 *
 * Usage:
 *   node ensure-routing.js --json '{"toolName":"wiki-api","toolType":"skill",...}'
 *   node ensure-routing.js --name wiki-api --type skill --keywords "wiki,confluence" \
 *     --desc "Confluence wiki ops" --when "prompt mentions wiki" \
 *     [--fallback "wiki-lite MCP"] [--never "WebFetch"] [--whyNot "login redirect"] \
 *     [--how "Skill tool: wiki-api read page_id=ID"]
 */
var utils = require('./setup-utils.js');

function parseArgs(argv) {
  var args = {};
  for (var i = 2; i < argv.length; i++) {
    if (argv[i] === '--json' && argv[i + 1]) {
      return JSON.parse(argv[++i]);
    }
    if (argv[i].startsWith('--') && argv[i + 1]) {
      var key = argv[i].slice(2);
      args[key] = argv[++i];
    }
  }
  // Map CLI flags to ensureRoutingInstruction opts
  return {
    toolName: args.name,
    toolType: args.type || 'skill',
    keywords: (args.keywords || '').split(',').map(function (k) { return k.trim(); }),
    description: args.desc || args.description,
    whenToUse: args.when || args.whenToUse,
    fallback: args.fallback,
    neverUse: args.never || args.neverUse,
    whyNot: args.whyNot,
    howToUse: args.how || args.howToUse
  };
}

var opts = parseArgs(process.argv);
if (!opts.toolName) {
  console.error('Error: --name (or --json) required');
  process.exit(1);
}

var result = utils.ensureRoutingInstruction(opts);
console.log(JSON.stringify(result, null, 2));
