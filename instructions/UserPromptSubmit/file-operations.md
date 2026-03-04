---
id: file-operations
keywords: [onedrive, read tool]
description: Never use Read tool. Use Write/Edit/Grep/Glob normally.
name: No Read tool
enabled: true
priority: 10
action: Never use Read tool. Use head/tail/cat via Bash to view files. Write/Edit/Grep/Glob are fine.
min_matches: 1
why: Read tool dumps file contents into context window causing multi-minute hangs in long sessions. Write/Edit are fast because they send content out.
---

# No Read Tool

## Never use the Read tool

Always use Bash to view file contents:

| Need | Command |
|------|---------|
| View whole file | `cat file.txt` |
| First N lines | `head -100 file.txt` |
| Last N lines | `tail -50 file.txt` |
| Specific lines | `sed -n '10,20p' file.txt` |

## These tools are fine

- **Write**: Always fast. Use for creating/overwriting files.
- **Edit**: Always fast. Use for targeted string replacements.
- **Grep**: Always fast. Returns matching lines only.
- **Glob**: Always fast. Returns file paths only.
