# Credential Manager

5th sub-manager. Stores API tokens/secrets in the OS credential store (Windows Credential Manager / macOS Keychain) instead of plaintext .env files.

## For Claude

- **NEVER cat/read .env files** - they may contain secrets
- **NEVER output credential values** in chat, logs, or memory
- To see what's stored: `python ~/.claude/super-manager/super_manager.py credentials list`
- To check health: `python ~/.claude/super-manager/super_manager.py credentials verify`
- To find plaintext tokens: `python ~/.claude/super-manager/super_manager.py credentials audit`

## For MCP Servers (Python)

Replace the .env loader with:

```python
import sys, os
sys.path.insert(0, os.path.expanduser('~/.claude/super-manager/credentials'))
from claude_cred import load_env
load_env()  # Auto-detects .env, resolves credential: prefixes
```

## For MCP Servers (Node.js)

```javascript
const path = require('path');
const os = require('os');
const { loadEnvFile } = require(
  path.join(os.homedir(), '.claude/super-manager/credentials/claude-cred.js')
);
loadEnvFile(__dirname + '/.env');
```

## .env Format

Non-secrets stay plaintext. Secrets use `credential:` prefix:

```
CONFLUENCE_URL=https://trendmicro.atlassian.net/wiki
CONFLUENCE_USERNAME=joel@trendmicro.com
CONFLUENCE_API_TOKEN=credential:wiki-lite/CONFLUENCE_API_TOKEN
```

## Storing Credentials (user runs these, NOT Claude)

```bash
# From clipboard (safest - no terminal history)
python super_manager.py credentials store wiki-lite/CONFLUENCE_API_TOKEN --clipboard

# Interactive prompt (hidden input)
python super_manager.py credentials store wiki-lite/CONFLUENCE_API_TOKEN

# Migrate entire .env file
python super_manager.py credentials migrate "/path/to/.env" wiki-lite
```

## Setup

```bash
python ~/.claude/super-manager/credentials/setup.py
```

Verifies keyring backend, tests credential store, scans for plaintext tokens.

## Architecture

```
credentials/
├── CLAUDE.md                   # This file
├── setup.py                    # One-click setup/verify
├── claude_cred.py              # Python helper (imported by servers/skills)
├── claude-cred.js              # Node.js helper (required by servers)
└── credential-registry.json    # Key name index (NO secrets)
```

All actual secret values live in:
- Windows: Credential Manager (Generic Credentials, service: claude-code)
- macOS: Keychain (service: claude-code)
