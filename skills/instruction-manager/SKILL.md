---
name: instruction-manager
description: "Manage context-aware instruction files - list, add, remove, enable, disable, match, export, import, backup, restore."
keywords:
  - instruction
  - instructions
  - context
  - frontmatter
  - matching
  - keyword
  - keywords
  - export
  - import
  - backup
  - restore
---

# Instruction Manager

Manage context-aware instruction .md files with YAML frontmatter. Part of super-manager.

## What Are Instructions?

Markdown files in `~/.claude/instructions/` organized by hook event. Each has YAML frontmatter with keywords -- when a prompt matches keywords, the instruction content is injected as context.

### Directory Structure

```
~/.claude/instructions/
├── UserPromptSubmit/     # Injected when prompt keywords match
│   ├── bash-scripting.md
│   ├── file-operations.md
│   └── ...
├── Stop/                 # Checked against Claude's response text
│   ├── fix-without-asking.md
│   └── ...
└── backups/              # Named snapshots for backup/restore
    ├── 20260222-143500/
    └── pre-restore-20260222-150000/
```

Single source of truth. No copies elsewhere.

### Frontmatter Format

```yaml
---
id: bash-scripting
name: Bash Scripting Safety
keywords: [bash, script, heredoc, js, javascript]
enabled: true
priority: 10
---
# Content here...
```

## WHY This System Exists

### The Problem: Context Drift
As Claude's context fills during long sessions, it enters "completion mode" -- rushing through work and ignoring instructions. CLAUDE.md instructions read at session start get buried. Claude stops following rules it read 50 messages ago.

### The Solution: Persistent Re-injection
tool-reminder.js (UserPromptSubmit hook) re-injects CLAUDE.md content on EVERY prompt as a system-reminder. Conditional instructions inject only when keywords match.

### Two Tiers
**Tier 1 - Global (CLAUDE.md):** Injected on EVERY prompt. Must be small (~45 lines). Rules that apply to ALL interactions.

**Tier 2 - Conditional (instruction files):** Injected only when prompt keywords match. Detailed "when X do Y" rules.

### The "Always Document WHY" Rule
Every instruction must explain WHY it exists, not just WHAT to do. When Claude understands the reason, it follows the spirit even in edge cases. Rules without reasoning become cargo cult.

## CRITICAL: Review Before Creating

1. List existing instructions in both UserPromptSubmit/ and Stop/
2. Read each relevant instruction to understand what it already covers
3. **Prefer modifying existing instructions** over creating new ones
4. Never duplicate functionality an existing instruction already handles

## Commands

### CRUD

```bash
# List all instructions
python ~/.claude/super-manager/super_manager.py instructions list

# Add a new instruction (default: UserPromptSubmit)
python ~/.claude/super-manager/super_manager.py instructions add INSTRUCTION_ID

# Remove (archives, never deletes)
python ~/.claude/super-manager/super_manager.py instructions remove INSTRUCTION_ID

# Enable/disable
python ~/.claude/super-manager/super_manager.py instructions enable INSTRUCTION_ID
python ~/.claude/super-manager/super_manager.py instructions disable INSTRUCTION_ID

# Verify all instructions healthy
python ~/.claude/super-manager/super_manager.py instructions verify

# Test keyword matching
python ~/.claude/super-manager/super_manager.py instructions match "some prompt text"
```

### Local Backup / Restore

Snapshot instructions locally. Try different sets without losing current ones:

```bash
# Backup (auto-named with timestamp)
python -c "from managers.instruction_manager import backup_instructions; print(backup_instructions())"

# Backup with a name
python -c "from managers.instruction_manager import backup_instructions; print(backup_instructions('before-experiment'))"

# List backups
python -c "from managers.instruction_manager import list_backups; [print(b['name'], '-', b['file_count'], 'files') for b in list_backups()['backups']]"

# Restore (auto-backs up current state first)
python -c "from managers.instruction_manager import restore_instructions; print(restore_instructions('before-experiment'))"
```

### Git Repo Backup / Restore

Register git repos as backup/restore targets. Each user maintains their own repo.
instruction-manager ships with a default repo URL for starter instructions, but users are never forced to use it.

```bash
# Add a repo
python -c "from managers.instruction_manager import add_repo; print(add_repo('grobomo/claude-code-instructions', 'default'))"

# Add your own repo
python -c "from managers.instruction_manager import add_repo; print(add_repo('myuser/my-instructions', 'personal'))"

# List repos
python -c "from managers.instruction_manager import list_repos; r = list_repos(); [print(repo['name'], '->', repo['url']) for repo in r['repos']]"

# Backup to repo (export, commit, push)
python -c "from managers.instruction_manager import backup_to_repo; print(backup_to_repo('personal'))"

# Restore from repo (pull, import -- skips existing by default)
python -c "from managers.instruction_manager import restore_from_repo; print(restore_from_repo('default'))"

# Restore with overwrite (archives existing first)
python -c "from managers.instruction_manager import restore_from_repo; print(restore_from_repo('default', overwrite=True))"

# Remove a repo
python -c "from managers.instruction_manager import remove_repo; print(remove_repo('default'))"
```

Repo structure mirrors the instruction directory:
```
my-instructions-repo/
├── UserPromptSubmit/
│   ├── bash-scripting.md
│   └── file-operations.md
├── Stop/
│   ├── fix-without-asking.md
│   └── no-reconfirm.md
└── README.md
```

### Auto Backup / Restore Hooks

Optional: auto-backup on session end, auto-restore on session start.
Both default to **false**. When enabled, creates hooks via hook-manager (dependency).

```bash
# Enable auto-restore from repos on session start
python -c "from managers.instruction_manager import set_auto_restore; print(set_auto_restore(True))"

# Enable auto-backup to repos on session end
python -c "from managers.instruction_manager import set_auto_backup; print(set_auto_backup(True))"

# Disable
python -c "from managers.instruction_manager import set_auto_restore; print(set_auto_restore(False))"
python -c "from managers.instruction_manager import set_auto_backup; print(set_auto_backup(False))"
```

## Current Instructions

### UserPromptSubmit (injected when prompt keywords match)

| ID | Keywords | Description |
|----|----------|-------------|
| background-tasks | background, task, zombie | Background task management |
| bash-scripting | bash, script, heredoc, js | Safe patterns for writing JS from bash |
| config-awareness | config, awareness, hash, registry | Config Awareness System details |
| credential-management | credential, secret, token | Credential store management |
| file-operations | file, write, edit, save | File operation rules |
| formatting | format, list, tree | Output formatting conventions |
| mcp-management | mcp, server, reload | MCP server management rules |
| no-emojis-use-ascii | output, emoji | ASCII art only, no emojis |
| review-instructions | never, always, stop, ! | Trigger instruction review on directive words |
| use-existing-tools | new, add, install | Check existing tools before building |
| write-js-from-bash | hook, script, js | Write JS via heredoc not Python |
| writing-instructions | instruction, keyword, meta | Meta-instruction for writing instructions |
| project-documentation | docs, readme, diagram | 3-layer documentation standard |

### Stop (checked against Claude's response text)

| ID | Match Type | Description |
|----|------------|-------------|
| fix-without-asking | pattern (regex) | Block "should I fix/test/update?" -- just do it |
| test-before-done | keywords | Block wrap-up without testing |
| no-reconfirm | pattern (regex) | Block re-asking what user already requested |

## Dependencies

- **super-manager** (`~/.claude/super-manager/`) -- core manager framework
- **hook-manager** -- required for auto-backup/restore hook creation (optional if not using auto hooks)
