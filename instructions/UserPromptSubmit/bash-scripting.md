---
id: bash-scripting
keywords: [heredoc, bash, script, javascript, node, write, js]
description: Safe patterns for writing JS/script files from bash on Windows/Git Bash
name: Safe patterns for writing JS/script files from bash on Windows/Git Bash
enabled: true
priority: 10
action: Use cat heredoc or base64 for JS files on Windows
---

# Bash Scripting Rules

## Writing JS Files

**Never use Python to write JS.** Python escapes `!` to `\!` and `\n` in triple-quotes corrupts JS string literals.

### Method 1: Cat Heredoc (preferred)
Write `.js` to `$TEMP/script.js` via cat heredoc, then run `node "$TEMP/script.js"`.
Use a UNIQUE delimiter (not EOF) to avoid content conflicts.

### Method 2: Generator Pattern
If JS content has single quotes that break the heredoc, write a generator `.js` that builds the target file line-by-line with `L.push()` and `fs.writeFileSync()`.

### Method 3: Base64 (last resort)
Base64-encode the content, decode with Node to write.

## Shell Environment
- **Git Bash is forced** - paths always use `/c/` style
- **Never use PowerShell** - escaping is broken
- Use `ls` not `dir`, `cat` not `type`
- Node sees Windows paths - use `path.join(process.env.TEMP, ...)` in Node
