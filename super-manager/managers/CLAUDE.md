# managers/

Sub-manager Python modules -- one per component type.

## Modules

| Module | Manages |
|--------|---------|
| `hook_manager.py` | Hook registry in `hooks/hook-registry.json` |
| `skill_manager.py` | Skill registry in `skills/skill-registry.json` |
| `mcp_server_manager.py` | MCP server entries in `servers.yaml` |
| `rule_manager.py` | Rule `.md` files in `rules/` |
| `credential_manager.py` | API tokens in OS credential store (keyring) |

## Common Interface

Each manager implements:
- `list_all()` - List registered items with status
- `add_item()` - Register a new item
- `remove_item()` - Unregister (archive, not delete)
- `enable_item()` / `disable_item()` - Toggle active state
- `verify_all()` - Cross-reference registry against filesystem

## Important

- Managers read/write registries but do not own the actual component files.
- All filesystem operations use `shared/file_operations.py`.
- Logging goes through `shared/logger.py`.
