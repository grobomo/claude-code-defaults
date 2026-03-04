---
id: review-before-modify
name: Review Before Modifying Rules
keywords: [stop, hook, modify, rule, edit, change, keyword, pattern]
description: Read all related hooks/rules before changing any
enabled: true
priority: 100
action: Read ALL stop hooks + rules before modifying any
---

# Review Before Modifying Rules or Stop Hooks

## WHY This Exists

Stop hooks and rules overlap in keywords and patterns. Editing one without seeing the others causes duplicate triggers, conflicting rules, and wasted context. Every modification must start with a full inventory.

## What To Do

Before modifying ANY rule or stop hook:

1. **Read ALL stop hooks** - `ls ~/.claude/rules/Stop/` then read each `.md` file
2. **Read ALL UserPromptSubmit rules** - `ls ~/.claude/rules/UserPromptSubmit/` then read related ones
3. **Check for keyword/pattern overlap** - identify which hooks already match the same phrases
4. **Then make changes** - with full context of what exists

## Do NOT

- Do NOT edit a stop hook without reading all 6 stop hooks first
- Do NOT add keywords that another hook already matches
- Do NOT create a new rule if an existing one covers the same trigger
