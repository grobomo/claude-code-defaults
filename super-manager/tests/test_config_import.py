"""
T3 - Tests for install_category() and do_import flow.

Covers:
- Install single file to target directory
- Install directory (is_directory=true)
- Skip conflicts in default mode
- Install conflicts in headless mode
- Skip conflicts in headless-safe mode
- Register hooks in settings.json from settings_entry
- Record installed state in installed.json
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.config_sync import (
    install_category,
    load_installed,
    record_installed,
    save_installed,
    compute_file_checksum,
)
from helpers import make_hook_item, make_manifest, make_skill_item


class TestInstallSingleFile:
    """Install a single file item to the target directory."""

    def test_file_copied_to_target(self, tmp_path, patch_paths):
        # Source file in repo
        repo = tmp_path / "repo" / "hooks"
        repo.mkdir(parents=True)
        (repo / "tool-reminder.js").write_text("// hook code", encoding="utf-8")

        # Empty target
        target = tmp_path / "target_hooks"
        target.mkdir()

        cat_config = {
            "path": "hooks/",
            "target": str(target),
            "merge_strategy": "skip_existing",
            "items": {
                "tool-reminder.js": make_hook_item("tool-reminder"),
            },
        }
        report_cat = {"to_add": [{"item_path": "tool-reminder.js"}], "conflicts": []}

        changes = install_category(
            "hooks", cat_config, str(tmp_path / "repo"), report_cat
        )

        assert (target / "tool-reminder.js").exists()
        assert (target / "tool-reminder.js").read_text(encoding="utf-8") == "// hook code"
        assert any(c["type"] == "added" for c in changes)

    def test_creates_parent_dirs(self, tmp_path, patch_paths):
        """Target subdirectories are created automatically."""
        repo = tmp_path / "repo" / "rules" / "UserPromptSubmit"
        repo.mkdir(parents=True)
        (repo / "bg.md").write_text("# bg", encoding="utf-8")

        target = tmp_path / "target_instr"
        target.mkdir()

        cat_config = {
            "path": "rules/",
            "target": str(target),
            "merge_strategy": "skip_existing",
            "items": {
                "UserPromptSubmit/bg.md": {
                    "checksum": "sha256:x",
                    "id": "bg",
                },
            },
        }

        changes = install_category(
            "rules", cat_config, str(tmp_path / "repo"), {"conflicts": []}
        )

        assert (target / "UserPromptSubmit" / "bg.md").exists()


class TestInstallDirectory:
    """Install a directory item (is_directory=true)."""

    def test_directory_copied(self, tmp_path, patch_paths):
        repo = tmp_path / "repo" / "skills" / "super-manager"
        repo.mkdir(parents=True)
        (repo / "SKILL.md").write_text("# SM", encoding="utf-8")
        (repo / "main.py").write_text("print(1)", encoding="utf-8")

        target = tmp_path / "target_skills"
        target.mkdir()

        cat_config = {
            "path": "skills/",
            "target": str(target),
            "merge_strategy": "skip_existing",
            "items": {
                "super-manager/": make_skill_item("super-manager"),
            },
        }

        changes = install_category(
            "skills", cat_config, str(tmp_path / "repo"), {"conflicts": []}
        )

        assert (target / "super-manager" / "SKILL.md").exists()
        assert (target / "super-manager" / "main.py").exists()
        assert any(c["type"] == "added" for c in changes)


class TestConflictHandling:
    """Test skip/overwrite behavior for conflicting items."""

    def _setup_conflict(self, tmp_path):
        """Create a conflict scenario: repo has one version, target has another."""
        repo = tmp_path / "repo" / "hooks"
        repo.mkdir(parents=True)
        (repo / "tool-reminder.js").write_text("// repo version", encoding="utf-8")

        target = tmp_path / "target"
        target.mkdir()
        (target / "tool-reminder.js").write_text("// user customized", encoding="utf-8")

        cat_config = {
            "path": "hooks/",
            "target": str(target),
            "merge_strategy": "skip_existing",
            "items": {
                "tool-reminder.js": make_hook_item("tool-reminder"),
            },
        }
        report_cat = {
            "conflicts": [{"item_path": "tool-reminder.js", "meta": {}}],
            "to_add": [],
        }
        return target, cat_config, report_cat

    def test_skip_conflicts_default_mode(self, tmp_path, patch_paths):
        """In default mode (no headless flags), conflicts are skipped."""
        target, cat_config, report_cat = self._setup_conflict(tmp_path)

        changes = install_category(
            "hooks", cat_config, str(tmp_path / "repo"), report_cat,
            headless=False, headless_safe=False,
        )

        # File should NOT be overwritten
        assert (target / "tool-reminder.js").read_text(encoding="utf-8") == "// user customized"
        assert len(changes) == 0

    def test_install_conflicts_headless_mode(self, tmp_path, patch_paths, fake_claude_dir):
        """In headless mode, conflicts ARE overwritten."""
        target, cat_config, report_cat = self._setup_conflict(tmp_path)

        changes = install_category(
            "hooks", cat_config, str(tmp_path / "repo"), report_cat,
            headless=True, headless_safe=False,
        )

        assert (target / "tool-reminder.js").read_text(encoding="utf-8") == "// repo version"
        assert any(c["type"] == "replaced" for c in changes)

    def test_skip_conflicts_headless_safe_mode(self, tmp_path, patch_paths):
        """In headless-safe mode, conflicts are skipped even though auto-approve."""
        target, cat_config, report_cat = self._setup_conflict(tmp_path)

        changes = install_category(
            "hooks", cat_config, str(tmp_path / "repo"), report_cat,
            headless=False, headless_safe=True,
        )

        assert (target / "tool-reminder.js").read_text(encoding="utf-8") == "// user customized"
        assert len(changes) == 0


class TestHookRegistration:
    """Hook items with settings_entry get registered in settings.json."""

    def test_hook_registered_in_settings(self, tmp_path, patch_paths, fake_claude_dir):
        repo = tmp_path / "repo" / "hooks"
        repo.mkdir(parents=True)
        (repo / "tool-reminder.js").write_text("// hook", encoding="utf-8")

        hooks_dir = fake_claude_dir / "hooks"

        cat_config = {
            "path": "hooks/",
            "target": str(hooks_dir),
            "merge_strategy": "skip_existing",
            "items": {
                "tool-reminder.js": make_hook_item("tool-reminder"),
            },
        }

        changes = install_category(
            "hooks", cat_config, str(tmp_path / "repo"), {"conflicts": []}
        )

        # Verify settings.json was updated
        settings_path = str(fake_claude_dir / "settings.json")
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)

        assert "hooks" in settings
        assert "UserPromptSubmit" in settings["hooks"]
        groups = settings["hooks"]["UserPromptSubmit"]
        commands = []
        for g in groups:
            for h in g.get("hooks", []):
                commands.append(h.get("command", ""))
        assert any("tool-reminder.js" in c for c in commands)

        # Should have a settings_hook_added change
        assert any(c["type"] == "settings_hook_added" for c in changes)

    def test_duplicate_hook_not_re_registered(self, tmp_path, patch_paths, fake_claude_dir):
        """If hook already in settings.json, don't add it again."""
        hooks_dir = fake_claude_dir / "hooks"
        settings_path = str(fake_claude_dir / "settings.json")

        # Pre-populate settings
        settings = {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {"type": "command", "command": f'node "{hooks_dir}/tool-reminder.js"'},
                        ],
                    }
                ]
            }
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f)

        repo = tmp_path / "repo" / "hooks"
        repo.mkdir(parents=True)
        (repo / "tool-reminder.js").write_text("// hook", encoding="utf-8")

        cat_config = {
            "path": "hooks/",
            "target": str(hooks_dir),
            "merge_strategy": "skip_existing",
            "items": {
                "tool-reminder.js": make_hook_item("tool-reminder"),
            },
        }

        install_category("hooks", cat_config, str(tmp_path / "repo"), {"conflicts": []})

        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)

        # Should still be exactly one hook entry, not duplicated
        all_hooks = []
        for g in settings["hooks"]["UserPromptSubmit"]:
            all_hooks.extend(g.get("hooks", []))
        reminder_hooks = [h for h in all_hooks if "tool-reminder.js" in h.get("command", "")]
        assert len(reminder_hooks) == 1


class TestRecordInstalled:
    """record_installed() writes installed.json correctly."""

    def test_record_basic(self, tmp_path, patch_paths, fake_claude_dir):
        target = str(fake_claude_dir / "hooks")
        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": target,
                "merge_strategy": "skip_existing",
                "items": {
                    "tool-reminder.js": make_hook_item("tool-reminder"),
                },
            },
        })
        changes = [
            {"type": "added", "path": os.path.join(target, "tool-reminder.js"), "backup": None},
            {"type": "settings_hook_added", "event": "UserPromptSubmit", "filename": "tool-reminder.js", "id": "tool-reminder"},
        ]

        record_installed("grobomo/claude-code-defaults", manifest, changes)

        installed = load_installed()
        slug = "grobomo--claude-code-defaults"
        assert slug in installed
        assert installed[slug]["version"] == "1.0.0"
        assert "hooks" in installed[slug]["categories"]

    def test_multiple_records_coexist(self, tmp_path, patch_paths, fake_claude_dir):
        target = str(fake_claude_dir / "hooks")
        manifest_a = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": target,
                "merge_strategy": "skip_existing",
                "items": {"a.js": make_hook_item("a")},
            },
        })
        manifest_b = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": target,
                "merge_strategy": "skip_existing",
                "items": {"b.js": make_hook_item("b")},
            },
        })

        record_installed("owner/repo-a", manifest_a, [
            {"type": "added", "path": os.path.join(target, "a.js"), "backup": None},
        ])
        record_installed("owner/repo-b", manifest_b, [
            {"type": "added", "path": os.path.join(target, "b.js"), "backup": None},
        ])

        installed = load_installed()
        assert "owner--repo-a" in installed
        assert "owner--repo-b" in installed
