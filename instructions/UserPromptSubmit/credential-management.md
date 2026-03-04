---
id: credential-management
keywords: [credential, api, key, token, secret, .env, password, plaintext]
tools: []
description: Credential management rules for secrets and API tokens
name: Credential management rules
enabled: true
priority: 10
action: Use credential-manager skill
---

# Credential Management Rules

- **NEVER read .env files** that may contain API tokens or secrets
- **NEVER output credential values** in chat, logs, or memory files
- Use `python ~/.claude/super-manager/super_manager.py credentials list` to see stored credentials (names only)
- Use `python ~/.claude/super-manager/super_manager.py credentials verify` to check health
- If a user needs to store a new token, tell them to run the store command themselves
- If plaintext tokens are found, suggest: `python super_manager.py credentials migrate <path> <service>`
- Helper library docs: `~/.claude/super-manager/credentials/CLAUDE.md`
