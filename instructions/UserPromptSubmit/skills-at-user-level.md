---
id: skills-at-user-level
name: Skills Always at User Level
keywords: [skill, create, new, make, template, scaffold]
description: "WHY: Project-level skills are hard to find across repos. WHAT: Always create skills at ~/.claude/skills/, never .claude/skills/."
enabled: true
priority: 10
action: Create skills at ~/.claude/skills/ (user level), never project level
min_matches: 2
---

# Skills Always at User Level

## WHY

Skills created at project level (.claude/skills/) are invisible from other projects and easy to lose track of. All skills should live at user level (~/.claude/skills/) so they're always available regardless of which project is open.

## Rule

When creating or moving skills:

1. **Always use `~/.claude/skills/`** as the target directory
2. **Never create skills in `.claude/skills/`** (project level)
3. If a project-level skill is found, move it to user level

## Do NOT

- Do NOT create skills in `.claude/skills/` (project directory)
- Do NOT assume project-level is correct because skill-maker defaults to it
