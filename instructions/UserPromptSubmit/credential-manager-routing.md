---
id: credential-manager-routing
name: credential-manager Routing
keywords: [credential, secret, token, key, password, .env, store]
enabled: true
priority: 10
action: Use credential-manager skill
---

# credential-manager Routing

## WHY
Store and retrieve API tokens/secrets in OS credential store. The credential-manager skill is already configured
and authenticated. Using it is faster and more reliable than generic tools.

## Rule
When prompt involves storing, retrieving, or managing API keys, tokens, or secrets:

1. **Use credential-manager skill** (preferred)
2. **Invoke via Skill tool**
4. **Never use Bash with echo/cat on .env files** for this -- exposes secrets in logs and conversation history


## How
```
Skill tool: credential-manager store SERVICE/KEY
```
