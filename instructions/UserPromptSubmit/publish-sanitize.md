---
id: publish-sanitize
name: Sanitize Before Publishing
keywords: [publish, marketplace, plugin, ship, push, deploy, skill, public, repo]
description: "WHY: Published plugins shipped with hardcoded personal paths that broke on other machines. WHAT: Mandatory sanitization scan before any publish to marketplace or public repo."
enabled: true
priority: 5
action: Scan for hardcoded paths before publishing
min_matches: 2
---

# Sanitize Before Publishing

## WHY

Published plugins contained hardcoded personal paths (`C:/Users/<username>/...`, `OneDrive - <OrgName>/...`,
personal GitHub usernames, test accounts). These paths break on every other machine and
leak org/identity info. This happened because the publish workflow copied local files without sanitization.

## Rule

Before committing files to any public or shared repo (marketplace, GitHub public, plugin publish):

### 1. Scan for personal paths

Run this check on ALL files being published:

```bash
grep -rn "C:/Users/<username>\|C:\\\\Users\\\\<username>\|OneDrive - <OrgName>\|<github-user>\|<test-account>" <dir> \
  --include="*.py" --include="*.js" --include="*.json" --include="*.md" \
  --include="*.sh" --include="*.yaml" --include="*.yml"
```

### 2. Fix any hits

| Pattern found | Replace with |
|--------------|-------------|
| `$HOME/.claude/...` | `$HOME/.claude/...` or `os.path.join(os.homedir(), '.claude', ...)` |
| `$HOME/projects/MCP` | Dynamic discovery via `glob` (see configuration_paths.py pattern) |
| `<github-username>` | Generic placeholder or env var |
| `<test-account>` | `my-account` or generic placeholder |
| `<personal-namespace>` | `my-namespace` or generic placeholder |
| Personal IPs, AWS account IDs | Remove or use `<your-ip>` placeholders |

### 3. Check registry/data files

Registry files (`hook-registry.json`, `skill-registry.json`, etc.) must be empty templates:
```json
{"hooks": [], "version": "1.0"}
```
These are populated at runtime by setup.js. Never ship pre-populated registries.

### 4. Verify no secrets

Also scan for tokens, API keys, passwords that might be in .env files or hardcoded:
```bash
grep -rn "TOKEN=\|KEY=\|SECRET=\|PASSWORD=" <dir> --include="*.py" --include="*.js" --include="*.json" --include="*.env"
```

## Do NOT

- Do NOT publish registry JSON files with hardcoded paths
- Do NOT ship .env files with actual credentials
- Do NOT include personal GitHub usernames in published plugin URLs
- Do NOT skip the scan -- "it's just a docstring" still breaks when someone reads the docs
