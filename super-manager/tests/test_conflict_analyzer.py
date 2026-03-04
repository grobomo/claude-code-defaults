"""
T2 - Tests for analyze_conflicts().

Covers:
- Fresh system (all items are to_add, no conflicts)
- Existing system with same checksums (all up_to_date)
- Existing system with different checksums (conflicts detected)
- Registry merge items (is_registry flag)
- Per-category grouping in report.categories
- Preserved items (user's files not in manifest)
- Existing hook systems detection (hooks in settings.json not in manifest)
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.config_sync import (
    analyze_conflicts,
    compute_dir_checksum,
    compute_file_checksum,
)
from helpers import (
    make_hook_item,
    make_rule_item,
    make_manifest,
    make_skill_item,
)


def _manifest_with_real_checksums(hooks_dir, skills_dir, rules_dir):
    """Build a manifest where checksums match the actual files on disk."""
    hook_ck = compute_file_checksum(os.path.join(str(hooks_dir), "tool-reminder.js"))
    skill_ck = compute_dir_checksum(os.path.join(str(skills_dir), "super-manager"))
    rule_ck = compute_file_checksum(os.path.join(str(rules_dir), "UserPromptSubmit", "background-tasks.md"))

    return make_manifest({
        "hooks": {
            "path": "hooks/",
            "target": str(hooks_dir),
            "merge_strategy": "skip_existing",
            "items": {
                "tool-reminder.js": make_hook_item("tool-reminder", checksum=hook_ck),
            },
        },
        "rules": {
            "path": "rules/",
            "target": str(rules_dir),
            "merge_strategy": "skip_existing",
            "items": {
                "UserPromptSubmit/background-tasks.md": make_rule_item(
                    "background-tasks", checksum=rule_ck
                ),
            },
        },
        "skills": {
            "path": "skills/",
            "target": str(skills_dir),
            "merge_strategy": "skip_existing",
            "items": {
                "super-manager/": make_skill_item("super-manager", checksum=skill_ck),
            },
        },
    })


class TestFreshSystem:
    """No existing files -- everything should be to_add."""

    def test_all_items_to_add(self, tmp_path, patch_paths):
        hooks_dir = tmp_path / "target_hooks"
        hooks_dir.mkdir()
        skills_dir = tmp_path / "target_skills"
        skills_dir.mkdir()
        rules_dir = tmp_path / "target_rules"
        rules_dir.mkdir()
        (rules_dir / "UserPromptSubmit").mkdir()

        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": str(hooks_dir),
                "merge_strategy": "skip_existing",
                "items": {
                    "tool-reminder.js": make_hook_item("tool-reminder"),
                },
            },
            "skills": {
                "path": "skills/",
                "target": str(skills_dir),
                "merge_strategy": "skip_existing",
                "items": {
                    "super-manager/": make_skill_item("super-manager"),
                },
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))

        assert len(report.to_add) == 2
        assert len(report.up_to_date) == 0
        assert len(report.conflicts) == 0

    def test_fresh_summary_counts(self, tmp_path, patch_paths):
        hooks_dir = tmp_path / "h"
        hooks_dir.mkdir()

        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": str(hooks_dir),
                "merge_strategy": "skip_existing",
                "items": {
                    "a.js": make_hook_item("a"),
                    "b.js": make_hook_item("b"),
                },
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))
        counts = report.summary_counts()

        assert counts["add"] == 2
        assert counts["up_to_date"] == 0
        assert counts["conflicts"] == 0


class TestUpToDate:
    """Files exist with matching checksums -- all should be up_to_date."""

    def test_matching_checksum_file(self, tmp_path, patch_paths):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook_file = hooks_dir / "tool-reminder.js"
        hook_file.write_text("console.log('hello');", encoding="utf-8")

        real_ck = compute_file_checksum(str(hook_file))

        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": str(hooks_dir),
                "merge_strategy": "skip_existing",
                "items": {
                    "tool-reminder.js": make_hook_item("tool-reminder", checksum=real_ck),
                },
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))

        assert len(report.up_to_date) == 1
        assert len(report.to_add) == 0
        assert len(report.conflicts) == 0

    def test_matching_checksum_directory(self, tmp_path, patch_paths):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        sm = skills_dir / "super-manager"
        sm.mkdir()
        (sm / "SKILL.md").write_text("# test", encoding="utf-8")

        real_ck = compute_dir_checksum(str(sm))

        manifest = make_manifest({
            "skills": {
                "path": "skills/",
                "target": str(skills_dir),
                "merge_strategy": "skip_existing",
                "items": {
                    "super-manager/": make_skill_item("super-manager", checksum=real_ck),
                },
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))
        assert len(report.up_to_date) == 1
        assert len(report.conflicts) == 0


class TestConflicts:
    """Files exist with different checksums -- should be detected as conflicts."""

    def test_different_checksum_is_conflict(self, tmp_path, patch_paths):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "tool-reminder.js").write_text("// customized", encoding="utf-8")

        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": str(hooks_dir),
                "merge_strategy": "skip_existing",
                "items": {
                    "tool-reminder.js": make_hook_item("tool-reminder", checksum="sha256:different"),
                },
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))
        assert len(report.conflicts) == 1
        assert report.conflicts[0]["item_path"] == "tool-reminder.js"

    def test_directory_different_checksum(self, tmp_path, patch_paths):
        skills_dir = tmp_path / "skills"
        sm = skills_dir / "super-manager"
        sm.mkdir(parents=True)
        (sm / "SKILL.md").write_text("# my custom version", encoding="utf-8")

        manifest = make_manifest({
            "skills": {
                "path": "skills/",
                "target": str(skills_dir),
                "merge_strategy": "skip_existing",
                "items": {
                    "super-manager/": make_skill_item("super-manager", checksum="sha256:old_checksum"),
                },
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))
        assert len(report.conflicts) == 1


class TestRegistryMerge:
    """Items with is_registry=True on checksum mismatch should go to to_merge."""

    def test_registry_item_mismatch_goes_to_merge(self, tmp_path, patch_paths):
        mcp_dir = tmp_path / "mcp"
        mcp_dir.mkdir()
        (mcp_dir / "servers.yaml").write_text("user_content: true", encoding="utf-8")

        manifest = make_manifest({
            "mcp-config": {
                "path": "mcp/",
                "target": str(mcp_dir),
                "merge_strategy": "merge_entries",
                "items": {
                    "servers.yaml": {
                        "checksum": "sha256:repo_version",
                        "id": "servers",
                        "is_registry": True,
                    },
                },
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))
        assert len(report.to_merge) == 1
        assert len(report.conflicts) == 0

    def test_registry_item_matching_checksum_is_up_to_date(self, tmp_path, patch_paths):
        mcp_dir = tmp_path / "mcp"
        mcp_dir.mkdir()
        (mcp_dir / "servers.yaml").write_text("content", encoding="utf-8")
        real_ck = compute_file_checksum(str(mcp_dir / "servers.yaml"))

        manifest = make_manifest({
            "mcp-config": {
                "path": "mcp/",
                "target": str(mcp_dir),
                "merge_strategy": "merge_entries",
                "items": {
                    "servers.yaml": {
                        "checksum": real_ck,
                        "id": "servers",
                        "is_registry": True,
                    },
                },
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))
        assert len(report.up_to_date) == 1
        assert len(report.to_merge) == 0


class TestCategoryGrouping:
    """Report.categories should mirror the per-category breakdown."""

    def test_categories_populated(self, tmp_path, patch_paths):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": str(hooks_dir),
                "merge_strategy": "skip_existing",
                "items": {"a.js": make_hook_item("a")},
            },
            "skills": {
                "path": "skills/",
                "target": str(skills_dir),
                "merge_strategy": "skip_existing",
                "items": {"my-skill/": make_skill_item("my-skill")},
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))

        assert "hooks" in report.categories
        assert "skills" in report.categories
        assert len(report.categories["hooks"]["to_add"]) == 1
        assert len(report.categories["skills"]["to_add"]) == 1

    def test_category_has_all_keys(self, tmp_path, patch_paths):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": str(hooks_dir),
                "merge_strategy": "skip_existing",
                "items": {"x.js": make_hook_item("x")},
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))
        cat = report.categories["hooks"]

        for key in ("to_add", "up_to_date", "conflicts", "to_merge", "preserved"):
            assert key in cat, f"Missing key '{key}' in category report"


class TestPreserved:
    """User's files not in manifest should appear in preserved list."""

    def test_user_hook_not_in_manifest(self, tmp_path, patch_paths):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "my-custom-hook.js").write_text("// mine", encoding="utf-8")
        (hooks_dir / "another.js").write_text("// also mine", encoding="utf-8")

        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": str(hooks_dir),
                "merge_strategy": "skip_existing",
                "items": {},  # manifest has NO hooks
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))
        preserved_paths = [p["item_path"] for p in report.preserved]

        assert "my-custom-hook.js" in preserved_paths
        assert "another.js" in preserved_paths

    def test_user_skill_dir_preserved(self, tmp_path, patch_paths):
        skills_dir = tmp_path / "skills"
        user_skill = skills_dir / "my-skill"
        user_skill.mkdir(parents=True)
        (user_skill / "SKILL.md").write_text("# mine", encoding="utf-8")

        manifest = make_manifest({
            "skills": {
                "path": "skills/",
                "target": str(skills_dir),
                "merge_strategy": "skip_existing",
                "items": {},
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))
        preserved_paths = [p["item_path"] for p in report.preserved]
        assert "my-skill/" in preserved_paths

    def test_dotfiles_and_archive_excluded_from_preserved(self, tmp_path, patch_paths):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / ".hidden.js").write_text("//", encoding="utf-8")
        (hooks_dir / "archive").mkdir()

        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": str(hooks_dir),
                "merge_strategy": "skip_existing",
                "items": {},
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))
        preserved_paths = [p["item_path"] for p in report.preserved]
        assert ".hidden.js" not in preserved_paths
        assert "archive" not in preserved_paths


class TestExistingHookSystems:
    """Detect hooks in settings.json that are not part of the manifest."""

    def test_detect_gsd_hooks(self, tmp_path, patch_paths, fake_claude_dir):
        import commands.config_sync as cs

        settings = {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {"type": "command", "command": 'node "C:/Users/test/.claude/hooks/gsd-gate.js"'},
                            {"type": "command", "command": 'node "C:/Users/test/.claude/hooks/auto-gsd.js"'},
                        ],
                    }
                ]
            }
        }
        settings_path = os.path.join(str(fake_claude_dir), "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f)

        # Manifest has no hooks
        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": str(fake_claude_dir / "hooks"),
                "merge_strategy": "skip_existing",
                "items": {},
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))

        filenames = [s["filename"] for s in report.existing_systems]
        assert "gsd-gate.js" in filenames
        assert "auto-gsd.js" in filenames

    def test_manifest_hooks_excluded_from_existing(self, tmp_path, patch_paths, fake_claude_dir):
        settings = {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {"type": "command", "command": 'node "C:/hooks/tool-reminder.js"'},
                            {"type": "command", "command": 'node "C:/hooks/gsd-gate.js"'},
                        ],
                    }
                ]
            }
        }
        settings_path = os.path.join(str(fake_claude_dir), "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f)

        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": str(fake_claude_dir / "hooks"),
                "merge_strategy": "skip_existing",
                "items": {
                    "tool-reminder.js": make_hook_item("tool-reminder"),
                },
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))

        filenames = [s["filename"] for s in report.existing_systems]
        # tool-reminder.js IS in manifest, should NOT show as existing
        assert "tool-reminder.js" not in filenames
        # gsd-gate.js is NOT in manifest, should show
        assert "gsd-gate.js" in filenames

    def test_no_settings_file_returns_empty(self, tmp_path, patch_paths, fake_claude_dir):
        """If settings.json is missing or empty, no existing systems detected."""
        settings_path = os.path.join(str(fake_claude_dir), "settings.json")
        os.remove(settings_path)

        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": str(fake_claude_dir / "hooks"),
                "merge_strategy": "skip_existing",
                "items": {},
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))
        assert report.existing_systems == []


class TestNullTarget:
    """Categories with no target (e.g. mcp with merge_entries)."""

    def test_merge_entries_category_goes_to_merge(self, tmp_path, patch_paths):
        manifest = make_manifest({
            "mcp": {
                "path": "mcp/",
                "target": None,
                "merge_strategy": "merge_entries",
                "items": {
                    "servers.yaml": {"checksum": "sha256:x", "id": "servers"},
                },
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))
        assert len(report.to_merge) == 1

    def test_null_target_non_merge_goes_to_add(self, tmp_path, patch_paths):
        manifest = make_manifest({
            "special": {
                "path": "special/",
                "target": None,
                "merge_strategy": "skip_existing",
                "items": {
                    "config.json": {"checksum": "sha256:x", "id": "config"},
                },
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))
        assert len(report.to_add) == 1
