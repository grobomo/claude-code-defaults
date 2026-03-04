# shared/

Shared Python modules used by all managers and commands.

## Modules

| Module | Purpose |
|--------|---------|
| `configuration_paths.py` | Resolves paths to config files (hooks, skills, servers.yaml, etc.) |
| `config_file_handler.py` | Read/write JSON and YAML config files with locking |
| `file_operations.py` | Filesystem operations (copy, move to archive, verify existence) |
| `logger.py` | Logging setup with standard format and per-component tags |
| `output_formatter.py` | Terminal output formatting (tables, trees, status indicators) |

## Important

- All managers import from here -- do not duplicate utility logic in managers.
- `configuration_paths.py` is the single source of truth for file locations.
- `file_operations.py` enforces the "never delete, always archive" rule.
