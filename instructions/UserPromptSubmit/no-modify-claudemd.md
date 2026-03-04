---
id: no-modify-claudemd
name: Never Modify CLAUDE.md - Use Rules Instead
keywords: [claude.md, CLAUDE.md, edit memo, update memo]
enabled: true
priority: 5
action: Create a rule file instead of modifying CLAUDE.md
min_matches: 1
---

# Never Modify CLAUDE.md -- Use Rules Instead

## WHY

CLAUDE.md is a static project memo maintained by the user. Adding rules, routing, or behavioral instructions to CLAUDE.md creates a monolithic file that's hard to manage, can't be individually toggled, and bypasses the keyword-matching rule system.

## Rule

When you need to persist new knowledge, routing, behavioral rules, or instructions:

1. **Create a rule file** in `~/.claude/rules/UserPromptSubmit/` (or the appropriate event folder)
2. **Use proper frontmatter** (id, name, keywords, action) per RULE-GUIDELINES
3. **NEVER edit CLAUDE.md** to add rules, routing, reminders, or behavioral instructions

## What Goes Where

| Content type | Where it lives |
|-------------|---------------|
| Behavioral rules ("always do X") | `~/.claude/rules/UserPromptSubmit/*.md` |
| Tool routing ("use skill Y for Z") | `~/.claude/rules/UserPromptSubmit/*-routing.md` |
| Stop corrections ("don't say X") | `~/.claude/rules/Stop/*.md` |
| Pre-tool gates ("block X before Y") | `~/.claude/rules/PreToolUse/*.md` |
| Project facts (IPs, URLs, architecture) | CLAUDE.md (this IS appropriate) |
| TODO lists, status, inventory | CLAUDE.md (this IS appropriate) |

## The Test

Ask: "Is this a RULE (behavioral/routing/enforcement) or a FACT (IP address, architecture, inventory)?"
- **Rule** -> rule file
- **Fact** -> CLAUDE.md is fine

## Do NOT

- Do NOT add "always do X" or "never do Y" to CLAUDE.md
- Do NOT add routing instructions to CLAUDE.md
- Do NOT add reminders or behavioral notes to CLAUDE.md
- Do NOT use memo-edit skill to add rules to CLAUDE.md
