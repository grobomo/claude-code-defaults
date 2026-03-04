"""
T8 - Tests for dynamic category processing.

Covers:
- Unknown category in manifest processed without KeyError
- Unknown category appears in report
- Install works for arbitrary category names
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.config_sync import (
    analyze_conflicts,
    format_report,
    install_category,
    validate_manifest,
)
from helpers import make_manifest


class TestUnknownCategoryAnalysis:
    """Unknown categories in manifest are processed without errors."""

    def test_unknown_category_no_keyerror(self, tmp_path, patch_paths):
        """Categories not in CATEGORY_MANAGER_MAP are handled gracefully."""
        target = tmp_path / "widgets"
        target.mkdir()

        manifest = make_manifest({
            "custom-widgets": {
                "path": "widgets/",
                "target": str(target),
                "merge_strategy": "skip_existing",
                "items": {
                    "widget-a.conf": {
                        "checksum": "sha256:widgetaaa",
                        "id": "widget-a",
                        "description": "Custom widget config",
                    },
                },
            },
        })

        # Should not raise KeyError
        report = analyze_conflicts(manifest, str(tmp_path))

        assert "custom-widgets" in report.categories
        assert len(report.to_add) == 1

    def test_multiple_unknown_categories(self, tmp_path, patch_paths):
        target_a = tmp_path / "things"
        target_a.mkdir()
        target_b = tmp_path / "stuff"
        target_b.mkdir()

        manifest = make_manifest({
            "things": {
                "path": "things/",
                "target": str(target_a),
                "merge_strategy": "skip_existing",
                "items": {
                    "thing1.yaml": {"checksum": "sha256:t1", "id": "t1"},
                    "thing2.yaml": {"checksum": "sha256:t2", "id": "t2"},
                },
            },
            "stuff": {
                "path": "stuff/",
                "target": str(target_b),
                "merge_strategy": "skip_existing",
                "items": {
                    "stuff.json": {"checksum": "sha256:s1", "id": "s1"},
                },
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))

        assert "things" in report.categories
        assert "stuff" in report.categories
        assert len(report.to_add) == 3

    def test_unknown_category_with_existing_files(self, tmp_path, patch_paths):
        """User has files in an unknown category target, handled gracefully."""
        target = tmp_path / "configs"
        target.mkdir()
        (target / "user-config.yaml").write_text("user: true", encoding="utf-8")

        manifest = make_manifest({
            "configs": {
                "path": "configs/",
                "target": str(target),
                "merge_strategy": "skip_existing",
                "items": {
                    "new-config.yaml": {"checksum": "sha256:nc", "id": "nc"},
                },
            },
        })

        report = analyze_conflicts(manifest, str(tmp_path))

        # new-config.yaml to add, user-config.yaml preserved
        assert len(report.to_add) == 1
        # Preserved detection for generic category scans files
        preserved_paths = [p["item_path"] for p in report.preserved]
        assert "user-config.yaml" in preserved_paths


class TestUnknownCategoryInReport:
    """Unknown categories appear correctly in formatted reports."""

    def test_unknown_category_in_report(self, tmp_path, patch_paths):
        manifest = make_manifest({
            "custom-widgets": {
                "path": "widgets/",
                "target": str(tmp_path / "widgets"),
                "merge_strategy": "skip_existing",
                "items": {
                    "w1.conf": {"checksum": "sha256:w1", "id": "w1"},
                },
            },
        })
        (tmp_path / "widgets").mkdir()

        report = analyze_conflicts(manifest, str(tmp_path))
        output = format_report(manifest, report, "owner/repo")

        assert "CUSTOM-WIDGETS" in output
        assert "[+]" in output
        assert "w1.conf" in output


class TestUnknownCategoryInstall:
    """Install works for arbitrary category names via generic file copy."""

    def test_install_unknown_category_file(self, tmp_path, patch_paths):
        """Files in unknown categories are copied via generic install path."""
        repo = tmp_path / "repo" / "widgets"
        repo.mkdir(parents=True)
        (repo / "widget-a.conf").write_text("widget_config=true", encoding="utf-8")

        target = tmp_path / "target_widgets"
        target.mkdir()

        cat_config = {
            "path": "widgets/",
            "target": str(target),
            "merge_strategy": "skip_existing",
            "items": {
                "widget-a.conf": {
                    "checksum": "sha256:xxx",
                    "id": "widget-a",
                },
            },
        }

        changes = install_category(
            "custom-widgets", cat_config, str(tmp_path / "repo"), {"conflicts": []}
        )

        assert (target / "widget-a.conf").exists()
        assert (target / "widget-a.conf").read_text(encoding="utf-8") == "widget_config=true"
        assert len(changes) == 1
        assert changes[0]["type"] == "added"

    def test_install_unknown_category_directory(self, tmp_path, patch_paths):
        """Directory items in unknown categories are copied correctly."""
        repo = tmp_path / "repo" / "blueprints" / "my-blueprint"
        repo.mkdir(parents=True)
        (repo / "config.yaml").write_text("name: bp", encoding="utf-8")
        (repo / "template.j2").write_text("{{ content }}", encoding="utf-8")

        target = tmp_path / "target_blueprints"
        target.mkdir()

        cat_config = {
            "path": "blueprints/",
            "target": str(target),
            "merge_strategy": "skip_existing",
            "items": {
                "my-blueprint/": {
                    "checksum": "sha256:bp1",
                    "id": "my-blueprint",
                    "is_directory": True,
                },
            },
        }

        changes = install_category(
            "blueprints", cat_config, str(tmp_path / "repo"), {"conflicts": []}
        )

        assert (target / "my-blueprint" / "config.yaml").exists()
        assert (target / "my-blueprint" / "template.j2").exists()
        assert len(changes) == 1

    def test_validate_accepts_unknown_categories(self):
        """validate_manifest() does not reject categories outside the known list."""
        manifest = make_manifest({
            "custom-widgets": {
                "path": "widgets/",
                "merge_strategy": "skip_existing",
                "items": {},
            },
            "blueprints": {
                "path": "blueprints/",
                "merge_strategy": "overwrite",
                "items": {},
            },
            "profiles": {
                "path": "profiles/",
                "merge_strategy": "skip_existing",
                "items": {},
            },
        })

        errors = validate_manifest(manifest)
        assert errors == []
