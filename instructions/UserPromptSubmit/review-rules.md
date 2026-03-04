---
id: review-rules
name: Review Rules
keywords: [next time, from now on, stop doing, never do, always do]
enabled: true
priority: 100
action: Use rule-manager skill
---
# Trigger: Review Rules

## WHY This Exists

When the user uses emotional or directive words (note, save, next time, stop, never, always, expletives, "!", "why"), they are expressing a persistent rule, frustration, or correction. These moments are exactly when rules should be reviewed and updated -- the user is telling you something they want to stick across sessions.

## What To Do

When you detect these trigger words in the user's prompt:

1. **Invoke rule-manager skill** (`/rule-manager`) to review existing rules
2. **Check if an existing rule covers the situation** -- if so, improve its keywords so it triggers better next time
3. **If no rule exists**, create a new one with:
   - Clear id and name
   - Keywords that would have caught this situation
   - WHY explanation so the rule transfers to edge cases
4. **Update both directories** (super-manager/instructions/ AND ~/.claude/rules/UserPromptSubmit/)

## Do NOT

- Do NOT create hooks -- the rule system already handles this
- Do NOT add rules to CLAUDE.md -- use rule files
- Do NOT ask the user how to fix it -- just fix it based on what they said
