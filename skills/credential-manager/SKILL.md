---

name: credential-manager
description: Store and retrieve API tokens/secrets in OS credential store (Windows Credential Manager / macOS Keychain)
keywords:
  - credential
  - secret
  - token
  - keyring
  - vault
  - password
  - api key
  - api_key
  - apikey
  - jwt
  - bearer
  - auth token
  - bot token
  - access key
  - secret key
  - private key
  - webhook secret
  - client secret
  - rdsec
  - openai key
  - anthropic key
  - telegram token
  - gateway token
  - encryption key
  - sops
  - kubectl create secret
  - from-literal
  - paste your key
  - paste your token
  - paste the token
  - enter your key
  - any of these come up: api key
  - bearer token
  - key api
  - token auth
  - token bot
  - key access
  - key secret
  - key private
  - secret webhook
  - secret client
  - key openai
  - key anthropic
  - token telegram
  - token gateway
  - key encryption
  - token bearer
  - securify
  - scan for secrets
  - hardcoded secrets
  - replace secrets
  - code secrets
---

# Credential Manager

Stores API tokens/secrets in the OS credential store instead of plaintext files. Self-contained -- works independently, no super-manager required.

## HARD RULES (non-negotiable)

- **NEVER** ask user to paste/type credentials in chat
- **NEVER** output credential values in chat, logs, or memory
- **NEVER** read .env files (may contain secrets)
- **NEVER** write secrets to plaintext files, YAML, JSON, or scripts
- **NEVER** put real credentials in kubectl commands, docker env flags, or shell variables
- **ALWAYS** use this skill when ANY of these come up: API key, token, secret, JWT, password, bearer token, webhook secret, client secret, access key, private key
- **ALWAYS** launch the GUI for storing new credentials -- never accept them as text input
- **ALWAYS** use `credential:` prefix in .env files for secret values
- When generating k8s secrets, deploy scripts, or docker commands that need credentials: reference the credential store, never hardcode values

## Storing Credentials

When user needs to store a token/key/secret:

1. Determine key name from context (e.g. "rdsec api key" -> `rdsec/API_KEY`)
2. Launch GUI: `python ~/.claude/skills/credential-manager/store_gui.py KEY_NAME`
3. If key name unclear, omit it -- GUI prompts for both name and value

GUI pops up with masked field. User pastes, clicks Store. Memory zeroed after.

## Retrieving Credentials (for scripts/deploys)

When a script or deploy needs a stored credential:

```bash
# Retrieve a credential value for use in a command (never echo it)
python -c "
import sys, os
sys.path.insert(0, os.path.expanduser('~/.claude/skills/credential-manager'))
from claude_cred import resolve
val = resolve('SERVICE/KEY')
if val: print(val)
" | <command-that-consumes-stdin>
```

For kubectl secrets:
```bash
# Create k8s secret from credential store (no plaintext)
python ~/.claude/skills/credential-manager/kubectl_secret.py \
  --name openclaw-secrets \
  --namespace my-namespace \
  --key rdsec/API_KEY:RDSEC_API_KEY \
  --key telegram/BOT_TOKEN:TELEGRAM_BOT_TOKEN \
  --key openclaw/GATEWAY_TOKEN:OPENCLAW_GATEWAY_TOKEN
```

## Commands

```bash
# Store (GUI popup)
python ~/.claude/skills/credential-manager/store_gui.py SERVICE/KEY

# List stored (names only)
python ~/.claude/skills/credential-manager/cred_cli.py list

# Verify store health
python ~/.claude/skills/credential-manager/cred_cli.py verify

# Audit .env files for plaintext secrets
python ~/.claude/skills/credential-manager/cred_cli.py audit

# Migrate .env to credential store
python ~/.claude/skills/credential-manager/cred_cli.py migrate "/path/.env" SERVICE

# Securify - scan code for hardcoded secrets, replace with keyring calls
python ~/.claude/skills/credential-manager/securify.py DIRECTORY --dry-run       # preview
python ~/.claude/skills/credential-manager/securify.py DIRECTORY --service NAME  # apply

# First-time setup
python ~/.claude/skills/credential-manager/setup.py
```

## Securify (Code Secret Scanner)

Scans Python, JS, YAML, and .env files for hardcoded API keys/tokens. For each secret found:
1. Stores the value in OS credential store
2. Replaces the hardcoded value with a `keyring.get_password()` call (Python) or `claude-cred.js` resolver (JS)
3. Creates `.bak` backup of each modified file

**Detects these patterns:**
- Python: `os.environ.get("KEY", "secret")`, `os.environ["KEY"]`, `API_KEY = "hardcoded"`
- JavaScript: `process.env.KEY || "default"`, `const KEY = "secret"`
- YAML: `api_key: sk-xxx` -> `api_key: credential:service/KEY`
- .env: `TOKEN=plaintext` -> `TOKEN=credential:service/TOKEN`

**Usage:**
```bash
# Preview what would change (safe, no modifications)
python ~/.claude/skills/credential-manager/securify.py /path/to/plugin --dry-run

# Apply replacements (creates .bak backups)
python ~/.claude/skills/credential-manager/securify.py /path/to/plugin --service my-plugin

# Service name auto-detected from directory name if not specified
python ~/.claude/skills/credential-manager/securify.py /path/to/my-plugin
```

**When to use:** Run this on any new plugin, skill, or MCP server before first use to eliminate hardcoded secrets.

## Integration

### .env files -- non-secrets stay plaintext, secrets use `credential:` prefix:
```
API_URL=https://example.com
API_TOKEN=credential:my-service/API_TOKEN
```

### Python (MCP servers/skills):
```python
import sys, os
sys.path.insert(0, os.path.expanduser('~/.claude/skills/credential-manager'))
from claude_cred import load_env
load_env()  # Resolves credential: prefixes from .env
```

### Node.js:
```javascript
const { loadEnvFile } = require(
  require('path').join(require('os').homedir(), '.claude/super-manager/credentials/claude-cred.js')
);
loadEnvFile(__dirname + '/.env');
```

## Storage

| Platform | Backend | Encryption |
|----------|---------|------------|
| Windows | Credential Manager (DPAPI) | AES-256 tied to user login |
| macOS | Keychain | AES-256 with secure enclave |

Service name: `claude-code`. Key format: `SERVICE/VARIABLE`.

## Files

```
~/.claude/skills/credential-manager/
├── SKILL.md                  # This file (skill definition + rules)
├── cred_cli.py               # Standalone CLI (list, verify, audit, migrate, securify, store)
├── securify.py               # Code secret scanner + keyring replacer
├── store_gui.py              # Secure GUI for storing credentials
├── claude_cred.py            # Python resolver (credential: prefix)
├── claude-cred.js            # Node.js resolver
├── kubectl_secret.py         # Create k8s secrets from credential store
├── credential-registry.json  # Key name index (no secrets)
└── setup.py                  # First-time setup + verification
```

Requires `keyring` Python package (auto-installed by setup.py).
