# claude-code-defaults

Default configuration for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) managed by [super-manager](https://github.com/grobomo/claude-code-skills).

## What's Included

| Category | Items | Description |
|----------|-------|-------------|
| **hooks** | 5 | Context injection, instruction loading, config awareness, enforcement |
| **instructions** | 10 | Behavioral rules loaded by keyword matching (UserPromptSubmit + Stop) |
| **skills** | 6 | Super-manager + 5 sub-managers (hooks, skills, instructions, credentials, MCP) |
| **credentials** | 5 | Credential tooling (CLI, GUI, Python/Node resolvers, security scanner) |
| **mcp** | 1 | Sample MCP server configurations |
| **claude-md** | 1 | Template CLAUDE.md with tool routing table |

## Install

```bash
# Import all defaults (interactive -- shows conflict report, asks y/n)
python ~/.claude/super-manager/super_manager.py config import grobomo/claude-code-defaults

# Non-interactive (skip conflicts)
python ~/.claude/super-manager/super_manager.py config import grobomo/claude-code-defaults --headless-safe
```

## How It Works

1. `config import` reads `manifest.json` to discover what's in the repo
2. Compares against your existing `~/.claude/` configuration
3. Shows a per-category conflict report
4. Installs non-conflicting items, skips conflicts
5. Records state in `~/.claude/super-manager/config/installed.json`

**Nothing is overwritten without approval.** Existing hooks, instructions, and skills are preserved.

## Uninstall

```bash
# Remove all items from this repo, restore originals
python ~/.claude/super-manager/super_manager.py config uninstall grobomo/claude-code-defaults
```

## Customization

Fork this repo, edit files, then:

```bash
# Register your fork
python ~/.claude/super-manager/super_manager.py config add-repo yourname/claude-code-defaults

# Import from your fork
python ~/.claude/super-manager/super_manager.py config import yourname/claude-code-defaults

# Push local changes back to your fork
python ~/.claude/super-manager/super_manager.py config export yourname/claude-code-defaults
```

## manifest.json

The manifest is the only file `config import` reads. It defines:
- **Categories**: dynamic dict (hooks, instructions, skills, etc.)
- **Items**: files/directories within each category
- **Checksums**: SHA256 for change detection
- **Merge strategy**: `skip_existing` (never overwrite) or `merge_entries` (additive merge)

Adding a new category = add a key to `manifest.json` + a folder. Zero code changes to super-manager.

## Auto-Checksums

A GitHub Action automatically recomputes manifest checksums on push to `main`.

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- [super-manager plugin](https://github.com/grobomo/claude-code-skills) installed
- `gh` CLI authenticated (`gh auth status`)
- Node.js (for hooks)
- Python 3.10+ (for credential tooling)
