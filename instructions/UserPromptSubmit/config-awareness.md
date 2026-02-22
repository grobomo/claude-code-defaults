---
id: config-awareness
name: Config Awareness System
keywords: [config, awareness, hash, registry, hook, skill, report, settings]
enabled: true
description: Config Awareness System - auto-loads config state, detects changes mid-session
---

# Config Awareness System

Auto-loads config state into context at session start, detects changes mid-session.

```
~/.claude/
├── config-report.md              # 3-manager dashboard (auto-generated)
├── hooks/
│   ├── config-awareness.js       # SessionStart: scans all 3 registries, writes report
│   ├── hook-registry.json        # Hook metadata (name, event, description, managed)
│   ├── skill-registry.json       # Skill metadata (id, name, keywords, managed)
│   ├── .config-hash              # MD5 hash for change detection
│   └── tool-reminder.js          # UserPromptSubmit: configCheck module detects changes
└── skills/
    └── hook-manager/SKILL.md     # Hook management skill
```

**3 Managers tracked:** Hook Manager (hook-registry.json), MCP Manager (servers.yaml), Skill Registry (skill-registry.json).
**Report:** `~/.claude/config-report.md` - managed/unmanaged counts, full inventory tables, rolling 20-entry change log.
**Hash alignment:** Both hooks normalize to `{ event, matcher, name, async }` / `{ name, enabled }` / `{ id, enabled }` before hashing.
