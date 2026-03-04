# commands/

Orchestration commands called via `super_manager.py` CLI router.

## Commands

| Command | Purpose |
|---------|---------|
| `status` | Quick health check -- counts of managed components, issues |
| `doctor` | Deep diagnostics -- orphaned entries, missing files, conflicts |
| `report` | Generate `reports/config-report.md` dashboard |
| `discover` | Scan filesystem, auto-register unmanaged components |
| `duplicates` | Find duplicate registrations across registries |

## Usage

```bash
python super_manager.py status
python super_manager.py doctor
python super_manager.py discover --auto
python super_manager.py report
python super_manager.py duplicates
```

## Important

- Each command is a separate Python module with a `run()` entry point.
- Commands orchestrate across all 4 managers, they do not manage components directly.
- Output is formatted via `shared/output_formatter.py`.
