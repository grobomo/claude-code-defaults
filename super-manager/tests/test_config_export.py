"""
T5 - Tests for do_export().

Covers:
- Copy local files to repo clone directory
- Recompute checksums and update manifest
- Handle directory items
"""
import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.config_sync import (
    compute_dir_checksum,
    compute_file_checksum,
    do_export,
    parse_manifest,
)
from helpers import make_hook_item, make_manifest, make_skill_item


def _create_repo_with_manifest(tmp_path, manifest):
    """Create a fake repo clone with .git dir and manifest.json."""
    repo = tmp_path / "config" / "repos" / "owner--repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()

    # Create subdirs per category
    for cat_name, cat_config in manifest.get("categories", {}).items():
        cat_path = repo / cat_config.get("path", "")
        cat_path.mkdir(parents=True, exist_ok=True)

    manifest_path = repo / "manifest.json"
    with open(str(manifest_path), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return str(repo)


class TestExportFiles:
    """Copy local files to repo clone directory."""

    def test_file_copied_to_repo(self, tmp_path, patch_paths, fake_claude_dir):
        hooks_dir = fake_claude_dir / "hooks"
        (hooks_dir / "tool-reminder.js").write_text("// local version", encoding="utf-8")

        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": str(hooks_dir),
                "merge_strategy": "skip_existing",
                "items": {
                    "tool-reminder.js": make_hook_item("tool-reminder", checksum="sha256:old"),
                },
            },
        })

        repo_dir = _create_repo_with_manifest(tmp_path, manifest)

        import commands.config_sync as cs
        # Point CONFIG_REPOS_DIR to our temp repos dir
        repos_dir = str(tmp_path / "config" / "repos")

        with patch.object(cs, "CONFIG_REPOS_DIR", repos_dir), \
             patch.object(cs, "_check_gh_cli", return_value=(True, "ok")), \
             patch("subprocess.run"):

            do_export("owner/repo")

        # File should be in repo clone
        exported = os.path.join(repo_dir, "hooks", "tool-reminder.js")
        assert os.path.isfile(exported)
        with open(exported, encoding="utf-8") as f:
            assert f.read() == "// local version"

    def test_checksum_updated_in_manifest(self, tmp_path, patch_paths, fake_claude_dir):
        hooks_dir = fake_claude_dir / "hooks"
        (hooks_dir / "tool-reminder.js").write_text("// v2 code", encoding="utf-8")

        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": str(hooks_dir),
                "merge_strategy": "skip_existing",
                "items": {
                    "tool-reminder.js": make_hook_item("tool-reminder", checksum="sha256:old"),
                },
            },
        })

        repo_dir = _create_repo_with_manifest(tmp_path, manifest)
        repos_dir = str(tmp_path / "config" / "repos")

        import commands.config_sync as cs

        with patch.object(cs, "CONFIG_REPOS_DIR", repos_dir), \
             patch.object(cs, "_check_gh_cli", return_value=(True, "ok")), \
             patch("subprocess.run"):

            do_export("owner/repo")

        # Re-read manifest, checksum should be updated
        updated_manifest = parse_manifest(os.path.join(repo_dir, "manifest.json"))
        new_ck = updated_manifest["categories"]["hooks"]["items"]["tool-reminder.js"]["checksum"]

        assert new_ck != "sha256:old"
        assert new_ck.startswith("sha256:")

        # Should match actual file checksum
        expected_ck = compute_file_checksum(os.path.join(repo_dir, "hooks", "tool-reminder.js"))
        assert new_ck == expected_ck


class TestExportDirectories:
    """Export directory items."""

    def test_directory_exported(self, tmp_path, patch_paths, fake_claude_dir):
        skills_dir = fake_claude_dir / "skills"
        sm = skills_dir / "super-manager"
        sm.mkdir()
        (sm / "SKILL.md").write_text("# Exported SM", encoding="utf-8")
        (sm / "main.py").write_text("print('export')", encoding="utf-8")

        manifest = make_manifest({
            "skills": {
                "path": "skills/",
                "target": str(skills_dir),
                "merge_strategy": "skip_existing",
                "items": {
                    "super-manager/": make_skill_item("super-manager", checksum="sha256:old_dir"),
                },
            },
        })

        repo_dir = _create_repo_with_manifest(tmp_path, manifest)
        repos_dir = str(tmp_path / "config" / "repos")

        import commands.config_sync as cs

        with patch.object(cs, "CONFIG_REPOS_DIR", repos_dir), \
             patch.object(cs, "_check_gh_cli", return_value=(True, "ok")), \
             patch("subprocess.run"):

            do_export("owner/repo")

        exported_dir = os.path.join(repo_dir, "skills", "super-manager")
        assert os.path.isdir(exported_dir)
        assert os.path.isfile(os.path.join(exported_dir, "SKILL.md"))
        assert os.path.isfile(os.path.join(exported_dir, "main.py"))

        # Verify checksum updated in manifest
        updated = parse_manifest(os.path.join(repo_dir, "manifest.json"))
        new_ck = updated["categories"]["skills"]["items"]["super-manager/"]["checksum"]
        assert new_ck != "sha256:old_dir"

        expected_ck = compute_dir_checksum(exported_dir)
        assert new_ck == expected_ck


class TestExportManifestTimestamp:
    """Export updates the manifest 'updated' timestamp."""

    def test_updated_timestamp_changes(self, tmp_path, patch_paths, fake_claude_dir):
        hooks_dir = fake_claude_dir / "hooks"
        (hooks_dir / "a.js").write_text("// a", encoding="utf-8")

        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": str(hooks_dir),
                "merge_strategy": "skip_existing",
                "items": {
                    "a.js": make_hook_item("a", checksum="sha256:old"),
                },
            },
        })
        manifest["updated"] = "2020-01-01T00:00:00Z"

        repo_dir = _create_repo_with_manifest(tmp_path, manifest)
        repos_dir = str(tmp_path / "config" / "repos")

        import commands.config_sync as cs

        with patch.object(cs, "CONFIG_REPOS_DIR", repos_dir), \
             patch.object(cs, "_check_gh_cli", return_value=(True, "ok")), \
             patch("subprocess.run"):

            do_export("owner/repo")

        updated = parse_manifest(os.path.join(repo_dir, "manifest.json"))
        assert updated["updated"] != "2020-01-01T00:00:00Z"


class TestExportMissingSources:
    """Missing local files don't crash export."""

    def test_missing_source_skipped(self, tmp_path, patch_paths, fake_claude_dir):
        """If user deleted the local file, export silently skips it."""
        hooks_dir = fake_claude_dir / "hooks"
        # Do NOT create the file on disk

        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": str(hooks_dir),
                "merge_strategy": "skip_existing",
                "items": {
                    "nonexistent.js": make_hook_item("nonexistent", checksum="sha256:old"),
                },
            },
        })

        repo_dir = _create_repo_with_manifest(tmp_path, manifest)
        repos_dir = str(tmp_path / "config" / "repos")

        import commands.config_sync as cs

        with patch.object(cs, "CONFIG_REPOS_DIR", repos_dir), \
             patch.object(cs, "_check_gh_cli", return_value=(True, "ok")), \
             patch("subprocess.run"):

            # Should not raise
            do_export("owner/repo")

        # File should not exist in repo either
        assert not os.path.isfile(os.path.join(repo_dir, "hooks", "nonexistent.js"))
