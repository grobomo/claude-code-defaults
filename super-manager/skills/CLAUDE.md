# skills/

Skill registry metadata for Super-Manager.

## Contents

- `skill-registry.json` - Registry of all managed skills (id, name, keywords, enabled)

## Important

- Super-Manager does NOT own skill folders. Actual skills live in `~/.claude/skills/`.
- This folder only contains the registry that tracks and cross-references them.
- Each skill entry maps an id to its name, keywords, and enabled state.
- `skill_manager.py` in `managers/` reads/writes this registry.
- Skills are normalized to `{ id, enabled }` for hash comparison.
- Keywords in the registry drive the matching logic in `tool-reminder.js`.
