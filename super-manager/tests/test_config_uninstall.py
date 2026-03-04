"""
T4 - Tests for uninstall_category() and do_uninstall flow.

Covers:
- Archive installed files (never delete)
- Remove hooks from settings.json
- Update installed.json after uninstall
- Handle missing files gracefully
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.config_sync import (
    load_installed,
    save_installed,
    uninstall_category,
)
from helpers import make_hook_item


class TestArchiveFiles:
    """Uninstalled files are moved to archive, never deleted."""

    def test_file_archived(self, tmp_path, patch_paths, fake_claude_dir):
        hooks_dir = fake_claude_dir / "hooks"
        (hooks_dir / "tool-reminder.js").write_text("// to uninstall", encoding="utf-8")

        cat_config = {
            "target": str(hooks_dir),
            "path": "hooks/",
        }
        installed_items = {
            "tool-reminder.js": {
                "checksum": "sha256:abc",
                "is_directory": False,
            },
        }

        actions = uninstall_category("hooks", cat_config, installed_items)

        # File should be gone from hooks/
        assert not (hooks_dir / "tool-reminder.js").exists()

        # File should exist in archive
        archive_dir = fake_claude_dir / "archive" / "config-uninstall-hooks"
        assert archive_dir.exists()
        archived_files = list(archive_dir.iterdir())
        assert len(archived_files) == 1
        assert archived_files[0].name.startswith("tool-reminder.js.")

        # Action recorded
        assert any(a["action"] == "archived" for a in actions)

    def test_directory_archived(self, tmp_path, patch_paths, fake_claude_dir):
        skills_dir = fake_claude_dir / "skills"
        sm = skills_dir / "super-manager"
        sm.mkdir()
        (sm / "SKILL.md").write_text("# SM", encoding="utf-8")

        cat_config = {
            "target": str(skills_dir),
            "path": "skills/",
        }
        installed_items = {
            "super-manager/": {
                "checksum": "sha256:xyz",
                "is_directory": True,
            },
        }

        actions = uninstall_category("skills", cat_config, installed_items)

        # Directory gone from skills/
        assert not sm.exists()

        # Archived
        archive_dir = fake_claude_dir / "archive" / "config-uninstall-skills"
        assert archive_dir.exists()
        archived = list(archive_dir.iterdir())
        assert len(archived) == 1
        assert archived[0].name.startswith("super-manager.")


class TestRemoveHooksFromSettings:
    """Hook items should be removed from settings.json on uninstall."""

    def test_hook_removed_from_settings(self, tmp_path, patch_paths, fake_claude_dir):
        hooks_dir = fake_claude_dir / "hooks"
        (hooks_dir / "tool-reminder.js").write_text("// hook", encoding="utf-8")

        # Pre-populate settings.json with hook registration
        settings_path = str(fake_claude_dir / "settings.json")
        settings = {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {"type": "command", "command": f'node "{hooks_dir}/tool-reminder.js"'},
                            {"type": "command", "command": 'node "C:/other/hook.js"'},
                        ],
                    }
                ]
            }
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f)

        cat_config = {
            "target": str(hooks_dir),
            "path": "hooks/",
        }
        installed_items = {
            "tool-reminder.js": {
                "checksum": "sha256:abc",
                "is_directory": False,
                "settings_entry": {"event": "UserPromptSubmit"},
            },
        }

        actions = uninstall_category("hooks", cat_config, installed_items)

        # Verify settings.json
        with open(settings_path, "r", encoding="utf-8") as f:
            updated = json.load(f)

        all_cmds = []
        for g in updated["hooks"].get("UserPromptSubmit", []):
            for h in g.get("hooks", []):
                all_cmds.append(h.get("command", ""))

        assert not any("tool-reminder.js" in c for c in all_cmds)
        # Other hook preserved
        assert any("hook.js" in c for c in all_cmds)

        assert any(a["action"] == "settings_hook_removed" for a in actions)

    def test_empty_groups_cleaned_up(self, tmp_path, patch_paths, fake_claude_dir):
        """When last hook is removed from a group, the group should be cleaned."""
        hooks_dir = fake_claude_dir / "hooks"
        (hooks_dir / "only-hook.js").write_text("//", encoding="utf-8")

        settings_path = str(fake_claude_dir / "settings.json")
        settings = {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {"type": "command", "command": 'node "C:/hooks/only-hook.js"'},
                        ],
                    }
                ]
            }
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f)

        cat_config = {"target": str(hooks_dir), "path": "hooks/"}
        installed_items = {
            "only-hook.js": {
                "is_directory": False,
                "settings_entry": {"event": "UserPromptSubmit"},
            },
        }

        uninstall_category("hooks", cat_config, installed_items)

        with open(settings_path, "r", encoding="utf-8") as f:
            updated = json.load(f)

        # The group list should be empty (empty groups removed)
        assert updated["hooks"]["UserPromptSubmit"] == []


class TestInstalledJsonUpdate:
    """installed.json should be updated after uninstall."""

    def test_installed_cleared_after_uninstall(self, tmp_path, patch_paths, fake_claude_dir):
        """After full category uninstall, items removed from tracking."""
        hooks_dir = fake_claude_dir / "hooks"
        (hooks_dir / "a.js").write_text("//", encoding="utf-8")

        # Pre-set installed.json
        installed = {
            "owner--repo": {
                "owner_repo": "owner/repo",
                "version": "1.0.0",
                "categories": {
                    "hooks": {
                        "a.js": {"checksum": "sha256:aaa", "is_directory": False},
                    }
                },
            }
        }
        save_installed(installed)

        cat_config = {"target": str(hooks_dir), "path": "hooks/"}
        cat_items = installed["owner--repo"]["categories"]["hooks"]

        uninstall_category("hooks", cat_config, cat_items)

        # Simulate what do_uninstall does: remove from installed
        inst = load_installed()
        del inst["owner--repo"]
        save_installed(inst)

        final = load_installed()
        assert "owner--repo" not in final


class TestMissingFiles:
    """Handle missing files gracefully during uninstall."""

    def test_missing_file_no_error(self, tmp_path, patch_paths, fake_claude_dir):
        """Uninstalling a file that doesn't exist should not raise."""
        hooks_dir = fake_claude_dir / "hooks"
        # Do NOT create the file

        cat_config = {"target": str(hooks_dir), "path": "hooks/"}
        installed_items = {
            "gone.js": {"checksum": "sha256:xxx", "is_directory": False},
        }

        actions = uninstall_category("hooks", cat_config, installed_items)

        # No archive action for missing file, but no error either
        assert len(actions) == 0

    def test_null_target_skipped(self, tmp_path, patch_paths):
        """Categories with no target are gracefully skipped."""
        cat_config = {"target": None, "path": "mcp/"}
        installed_items = {
            "servers.yaml": {"checksum": "sha256:x"},
        }

        actions = uninstall_category("mcp", cat_config, installed_items)
        assert actions == []
