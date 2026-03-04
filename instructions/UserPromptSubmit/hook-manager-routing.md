---
id: hook-manager-routing
name: hook-manager Routing
keywords: [hook, manage, add, remove, enable, disable, debug]
enabled: true
priority: 10
action: Use hook-manager skill
---

# hook-manager Routing

## WHY
Create and manage Claude Code hooks with correct schema and contracts. The hook-manager skill is already configured
and authenticated. Using it is faster and more reliable than generic tools.

## Rule
When prompt involves creating, editing, enabling, or debugging hooks:

1. **Use hook-manager skill** (preferred)
2. **Invoke via Skill tool**


## How
```
Skill tool: hook-manager add my-hook --event UserPromptSubmit
```
