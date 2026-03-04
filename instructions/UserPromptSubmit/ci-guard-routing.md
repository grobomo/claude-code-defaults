---
id: ci-guard-routing
name: CI Guard Routing
keywords: [ci, guard, quality, gate, actions, workflow, compliance, sanitize, block, pr]
description: "WHY: Manual sanitization rules are unreliable -- Claude can forget, users can skip. WHAT: Route to ci-guard skill for GitHub Actions quality gates that block bad PRs automatically."
enabled: true
priority: 10
action: Route to ci-guard skill for GitHub Actions quality gates
min_matches: 2
---

# CI Guard Routing

## WHY

Claude rules and SKILL.md sanitization sections are advisory -- they rely on Claude reading and following instructions. GitHub Actions quality gates are enforcement -- PRs with personal paths or secrets cannot merge, period.

## Rule

When prompt involves setting up CI checks, quality gates, PR validation, or sanitization enforcement:

1. **Use ci-guard skill** (preferred)
2. **Invoke via Skill tool**

## How

```
Skill tool: ci-guard [--marketplace] [--paths-only]
```
