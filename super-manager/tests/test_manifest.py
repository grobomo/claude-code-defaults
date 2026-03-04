"""
T1 - Tests for parse_manifest() and validate_manifest().

Covers:
- Parse valid manifest.json
- Validate schema: reject missing 'version', missing 'categories',
  missing 'path'/'items'/'merge_strategy' per category
- Iterate categories dynamically
- Accept valid manifest with multiple categories
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.config_sync import parse_manifest, validate_manifest
from helpers import SAMPLE_MANIFEST, make_manifest


class TestParseManifest:
    """Tests for parse_manifest()."""

    def test_parse_valid_manifest(self, tmp_path):
        """Parse a well-formed manifest.json and get a dict back."""
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(SAMPLE_MANIFEST), encoding="utf-8")

        result = parse_manifest(str(path))

        assert result["version"] == "1.0.0"
        assert "categories" in result
        assert "hooks" in result["categories"]
        assert "rules" in result["categories"]
        assert "skills" in result["categories"]

    def test_parse_preserves_item_metadata(self, tmp_path):
        """Parsed manifest keeps nested item metadata intact."""
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(SAMPLE_MANIFEST), encoding="utf-8")

        result = parse_manifest(str(path))
        hook_item = result["categories"]["hooks"]["items"]["tool-reminder.js"]

        assert hook_item["checksum"] == "sha256:abc123"
        assert hook_item["id"] == "tool-reminder"
        assert hook_item["settings_entry"]["event"] == "UserPromptSubmit"

    def test_parse_nonexistent_file_raises(self, tmp_path):
        """Parsing a missing file raises an exception."""
        with pytest.raises((FileNotFoundError, IOError)):
            parse_manifest(str(tmp_path / "nope.json"))

    def test_parse_invalid_json_raises(self, tmp_path):
        """Parsing malformed JSON raises an exception."""
        path = tmp_path / "manifest.json"
        path.write_text("{broken json", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            parse_manifest(str(path))


class TestValidateManifest:
    """Tests for validate_manifest()."""

    def test_valid_manifest_no_errors(self):
        """A complete manifest returns an empty error list."""
        errors = validate_manifest(SAMPLE_MANIFEST)
        assert errors == []

    def test_missing_version(self):
        """Missing 'version' field produces an error."""
        manifest = {"categories": {"hooks": {"path": "h/", "merge_strategy": "skip", "items": {}}}}
        errors = validate_manifest(manifest)
        assert any("version" in e.lower() for e in errors)

    def test_missing_categories(self):
        """Missing 'categories' field produces an error."""
        manifest = {"version": "1.0.0"}
        errors = validate_manifest(manifest)
        assert any("categories" in e.lower() for e in errors)

    def test_categories_not_a_dict(self):
        """'categories' as a list instead of dict produces an error."""
        manifest = {"version": "1.0.0", "categories": ["hooks", "skills"]}
        errors = validate_manifest(manifest)
        assert any("dict" in e.lower() for e in errors)

    def test_missing_path_in_category(self):
        """Category without 'path' produces an error."""
        manifest = make_manifest({
            "hooks": {"merge_strategy": "skip_existing", "items": {}},
        })
        errors = validate_manifest(manifest)
        assert any("path" in e.lower() and "hooks" in e.lower() for e in errors)

    def test_missing_merge_strategy_in_category(self):
        """Category without 'merge_strategy' produces an error."""
        manifest = make_manifest({
            "hooks": {"path": "hooks/", "items": {}},
        })
        errors = validate_manifest(manifest)
        assert any("merge_strategy" in e.lower() for e in errors)

    def test_missing_items_in_category(self):
        """Category without 'items' produces an error."""
        manifest = make_manifest({
            "hooks": {"path": "hooks/", "merge_strategy": "skip_existing"},
        })
        errors = validate_manifest(manifest)
        assert any("items" in e.lower() for e in errors)

    def test_items_not_a_dict(self):
        """Items as a list instead of dict produces an error."""
        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "merge_strategy": "skip_existing",
                "items": ["file1.js", "file2.js"],
            },
        })
        errors = validate_manifest(manifest)
        assert any("items" in e.lower() and "dict" in e.lower() for e in errors)

    def test_multiple_categories_all_valid(self):
        """Manifest with multiple valid categories passes validation."""
        manifest = make_manifest({
            "hooks": {"path": "hooks/", "merge_strategy": "skip_existing", "items": {}},
            "skills": {"path": "skills/", "merge_strategy": "skip_existing", "items": {}},
            "rules": {"path": "rules/", "merge_strategy": "skip_existing", "items": {}},
            "mcp": {"path": "mcp/", "merge_strategy": "merge_entries", "items": {}},
        })
        errors = validate_manifest(manifest)
        assert errors == []

    def test_multiple_categories_some_invalid(self):
        """Multiple categories with mixed validity produce errors only for bad ones."""
        manifest = make_manifest({
            "hooks": {"path": "hooks/", "merge_strategy": "skip_existing", "items": {}},
            "skills": {"merge_strategy": "skip_existing", "items": {}},  # missing path
            "mcp": {"path": "mcp/", "items": {}},  # missing merge_strategy
        })
        errors = validate_manifest(manifest)
        assert len(errors) == 2
        assert any("skills" in e and "path" in e for e in errors)
        assert any("mcp" in e and "merge_strategy" in e for e in errors)

    def test_iterates_categories_dynamically(self):
        """Validation iterates over arbitrary category names (not hardcoded)."""
        manifest = make_manifest({
            "custom-widget": {"path": "widgets/", "merge_strategy": "overwrite", "items": {}},
            "another-thing": {"path": "things/", "merge_strategy": "skip_existing", "items": {}},
        })
        errors = validate_manifest(manifest)
        assert errors == []

    def test_empty_categories_is_valid(self):
        """Empty categories dict is valid (nothing to install)."""
        manifest = make_manifest({})
        errors = validate_manifest(manifest)
        assert errors == []
