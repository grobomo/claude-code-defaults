---
id: credential-management
keywords: [credential, api, key, token, secret, env, plaintext, password, store, expired, rotate, securify]
description: Credential management rules for secrets and API tokens
name: Credential management rules
enabled: true
priority: 10
---

# Credential Management Instructions

- **NEVER read .env files** that may contain API tokens or secrets
- **NEVER output credential values** in chat, logs, or memory files
- Use `python ~/.claude/skills/credential-manager/cred_cli.py list` to see stored credentials (names only)
- Use `python ~/.claude/skills/credential-manager/cred_cli.py verify` to check health
- If a user needs to store a new token, tell them to run the store command themselves:
  `python ~/.claude/skills/credential-manager/store_gui.py SERVICE/KEY`
- If plaintext tokens found in .env: `python ~/.claude/skills/credential-manager/cred_cli.py migrate <path> <service>`
- To scan code for hardcoded secrets: `python ~/.claude/skills/credential-manager/securify.py <dir> --dry-run`
