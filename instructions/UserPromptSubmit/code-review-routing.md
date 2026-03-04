---
id: code-review-routing
name: code-review Routing
keywords: [review, audit, consistency, stale, secrets, drift, phantom]
enabled: true
priority: 10
action: Use code-review skill
---

# code-review Routing

## WHY
Automated config consistency, secret scanning, and security review. The code-review skill is already configured
and authenticated. Using it is faster and more reliable than generic tools.

## Rule
When prompt involves reviewing config, finding stale references, auditing secrets, or security scanning:

1. **Use code-review skill** (preferred)
2. **Invoke via Skill tool**
4. **Never use manual grep across config files** for this -- code-review automates all checks with structured output and credential-manager integration


## How
```
Skill tool: code-review [path] [--secrets-only] [--config-only]
```
