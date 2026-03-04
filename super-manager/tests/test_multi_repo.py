"""
T7 - Tests for multi-repo support.

Covers:
- Register multiple repos in repos.json
- Import from both repos
- Uninstall one repo's items while other persists
- repos.json and installed.json stay consistent
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.config_sync import (
    _register_repo,
    _repo_slug,
    install_category,
    load_installed,
    load_repos,
    record_installed,
    save_installed,
    save_repos,
    uninstall_category,
)
from helpers import make_hook_item, make_manifest, make_skill_item


class TestRegisterMultipleRepos:
    """repos.json can hold multiple repo entries."""

    def test_register_two_repos(self, tmp_path, patch_paths):
        _register_repo("owner/repo-a")
        _register_repo("owner/repo-b")

        repos = load_repos()
        names = [r["owner_repo"] for r in repos]

        assert "owner/repo-a" in names
        assert "owner/repo-b" in names
        assert len(repos) == 2

    def test_duplicate_registration_idempotent(self, tmp_path, patch_paths):
        _register_repo("owner/repo-a")
        _register_repo("owner/repo-a")

        repos = load_repos()
        assert len(repos) == 1

    def test_repo_has_alias(self, tmp_path, patch_paths):
        _register_repo("grobomo/claude-code-defaults")

        repos = load_repos()
        assert repos[0]["alias"] == "claude-code-defaults"

    def test_repo_has_added_date(self, tmp_path, patch_paths):
        _register_repo("owner/repo")

        repos = load_repos()
        assert "added_date" in repos[0]
        assert len(repos[0]["added_date"]) > 10  # ISO format


class TestImportFromBothRepos:
    """Install items from two different repos, tracked separately in installed.json."""

    def test_items_from_two_repos(self, tmp_path, patch_paths, fake_claude_dir):
        hooks_dir = fake_claude_dir / "hooks"
        skills_dir = fake_claude_dir / "skills"

        # Repo A provides hooks
        repo_a = tmp_path / "repo_a" / "hooks"
        repo_a.mkdir(parents=True)
        (repo_a / "hook-a.js").write_text("// from repo A", encoding="utf-8")

        cat_config_a = {
            "path": "hooks/",
            "target": str(hooks_dir),
            "merge_strategy": "skip_existing",
            "items": {"hook-a.js": make_hook_item("hook-a")},
        }
        manifest_a = make_manifest({"hooks": cat_config_a})

        changes_a = install_category(
            "hooks", cat_config_a, str(tmp_path / "repo_a"), {"conflicts": []}
        )
        record_installed("owner/repo-a", manifest_a, changes_a)

        # Repo B provides skills
        repo_b = tmp_path / "repo_b" / "skills" / "my-skill"
        repo_b.mkdir(parents=True)
        (repo_b / "SKILL.md").write_text("# From repo B", encoding="utf-8")

        cat_config_b = {
            "path": "skills/",
            "target": str(skills_dir),
            "merge_strategy": "skip_existing",
            "items": {"my-skill/": make_skill_item("my-skill")},
        }
        manifest_b = make_manifest({"skills": cat_config_b})

        changes_b = install_category(
            "skills", cat_config_b, str(tmp_path / "repo_b"), {"conflicts": []}
        )
        record_installed("owner/repo-b", manifest_b, changes_b)

        installed = load_installed()
        assert "owner--repo-a" in installed
        assert "owner--repo-b" in installed
        assert "hooks" in installed["owner--repo-a"]["categories"]
        assert "skills" in installed["owner--repo-b"]["categories"]


class TestUninstallOneRepoKeepsOther:
    """Uninstalling one repo's items doesn't affect the other."""

    def test_other_repo_persists(self, tmp_path, patch_paths, fake_claude_dir):
        hooks_dir = fake_claude_dir / "hooks"

        # Install items from both repos
        (hooks_dir / "hook-a.js").write_text("// A", encoding="utf-8")
        (hooks_dir / "hook-b.js").write_text("// B", encoding="utf-8")

        installed = {
            "owner--repo-a": {
                "owner_repo": "owner/repo-a",
                "version": "1.0.0",
                "categories": {
                    "hooks": {
                        "hook-a.js": {"checksum": "sha256:aaa", "is_directory": False},
                    },
                },
            },
            "owner--repo-b": {
                "owner_repo": "owner/repo-b",
                "version": "1.0.0",
                "categories": {
                    "hooks": {
                        "hook-b.js": {"checksum": "sha256:bbb", "is_directory": False},
                    },
                },
            },
        }
        save_installed(installed)

        # Uninstall repo A
        cat_config = {"target": str(hooks_dir), "path": "hooks/"}
        uninstall_category("hooks", cat_config, installed["owner--repo-a"]["categories"]["hooks"])

        # Remove repo-a from installed (simulating do_uninstall)
        inst = load_installed()
        del inst["owner--repo-a"]
        save_installed(inst)

        # Verify
        final = load_installed()
        assert "owner--repo-a" not in final
        assert "owner--repo-b" in final

        # hook-a.js archived, hook-b.js still there
        assert not (hooks_dir / "hook-a.js").exists()
        assert (hooks_dir / "hook-b.js").exists()


class TestConsistency:
    """repos.json and installed.json stay consistent."""

    def test_repos_and_installed_match(self, tmp_path, patch_paths, fake_claude_dir):
        """After registering and installing, both files reference the same repos."""
        hooks_dir = fake_claude_dir / "hooks"

        _register_repo("owner/repo-a")
        _register_repo("owner/repo-b")

        repo_a = tmp_path / "repo_a" / "hooks"
        repo_a.mkdir(parents=True)
        (repo_a / "a.js").write_text("//", encoding="utf-8")

        cat_a = {
            "path": "hooks/",
            "target": str(hooks_dir),
            "merge_strategy": "skip_existing",
            "items": {"a.js": make_hook_item("a")},
        }
        manifest_a = make_manifest({"hooks": cat_a})

        changes = install_category("hooks", cat_a, str(tmp_path / "repo_a"), {"conflicts": []})
        record_installed("owner/repo-a", manifest_a, changes)

        repos = load_repos()
        installed = load_installed()

        repo_names = {r["owner_repo"] for r in repos}
        installed_repos = {v["owner_repo"] for v in installed.values()}

        # repo-a should be in both
        assert "owner/repo-a" in repo_names
        assert "owner/repo-a" in installed_repos

        # repo-b registered but not installed
        assert "owner/repo-b" in repo_names
        assert "owner/repo-b" not in installed_repos

    def test_remove_from_repos_keeps_installed(self, tmp_path, patch_paths):
        """Removing a repo from repos.json doesn't delete installed.json entries.
        (do_uninstall handles that separately.)"""
        _register_repo("owner/repo-a")

        installed = {
            "owner--repo-a": {
                "owner_repo": "owner/repo-a",
                "version": "1.0.0",
                "categories": {},
            }
        }
        save_installed(installed)

        # Remove from repos
        repos = load_repos()
        repos = [r for r in repos if r["owner_repo"] != "owner/repo-a"]
        save_repos(repos)

        # installed.json should still have it
        inst = load_installed()
        assert "owner--repo-a" in inst

    def test_slug_conversion(self):
        """owner/repo slugs are consistent."""
        assert _repo_slug("grobomo/claude-code-defaults") == "grobomo--claude-code-defaults"
        assert _repo_slug("owner/repo") == "owner--repo"
        assert _repo_slug("a/b") == "a--b"
