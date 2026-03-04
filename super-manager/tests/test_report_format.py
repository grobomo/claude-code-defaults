"""
T6 - Tests for format_report().

Covers:
- Report grouped by category
- Each section shows existing/add/conflict/merge/up-to-date
- Summary line with correct counts
- Conflicts message shown when conflicts > 0
- Existing systems shown in hooks section
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.config_sync import ConflictReport, format_report
from helpers import make_hook_item, make_manifest, make_skill_item


def _build_report(to_add=None, up_to_date=None, conflicts=None, to_merge=None,
                  preserved=None, existing_systems=None, categories=None):
    """Helper to create a ConflictReport with specific data."""
    report = ConflictReport()
    report.to_add = to_add or []
    report.up_to_date = up_to_date or []
    report.conflicts = conflicts or []
    report.to_merge = to_merge or []
    report.preserved = preserved or []
    report.existing_systems = existing_systems or []
    report.categories = categories or {}
    return report


class TestCategoryGrouping:
    """Report is grouped by category with clear section headers."""

    def test_each_category_has_header(self):
        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": "~/.claude/hooks/",
                "merge_strategy": "skip_existing",
                "items": {"a.js": make_hook_item("a")},
            },
            "skills": {
                "path": "skills/",
                "target": "~/.claude/skills/",
                "merge_strategy": "skip_existing",
                "items": {"sm/": make_skill_item("sm")},
            },
        })

        report = _build_report(
            to_add=[
                {"category": "hooks", "item_path": "a.js", "meta": make_hook_item("a")},
                {"category": "skills", "item_path": "sm/", "meta": make_skill_item("sm")},
            ],
            categories={
                "hooks": {"to_add": [{"item_path": "a.js", "meta": make_hook_item("a")}],
                           "up_to_date": [], "conflicts": [], "to_merge": [], "preserved": []},
                "skills": {"to_add": [{"item_path": "sm/", "meta": make_skill_item("sm")}],
                            "up_to_date": [], "conflicts": [], "to_merge": [], "preserved": []},
            },
        )

        output = format_report(manifest, report, "owner/repo")

        assert "HOOKS" in output
        assert "SKILLS" in output

    def test_header_includes_item_count(self):
        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": "~/.claude/hooks/",
                "merge_strategy": "skip_existing",
                "items": {
                    "a.js": make_hook_item("a"),
                    "b.js": make_hook_item("b"),
                    "c.js": make_hook_item("c"),
                },
            },
        })

        report = _build_report(
            categories={
                "hooks": {"to_add": [], "up_to_date": [], "conflicts": [], "to_merge": [], "preserved": []},
            },
        )

        output = format_report(manifest, report, "owner/repo")
        assert "3 items" in output


class TestSectionContent:
    """Each section shows the correct type of items."""

    def test_add_items_shown(self):
        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": "~/.claude/hooks/",
                "merge_strategy": "skip_existing",
                "items": {"new-hook.js": make_hook_item("new-hook")},
            },
        })

        report = _build_report(
            to_add=[{"category": "hooks", "item_path": "new-hook.js", "meta": make_hook_item("new-hook")}],
            categories={
                "hooks": {
                    "to_add": [{"item_path": "new-hook.js", "meta": make_hook_item("new-hook")}],
                    "up_to_date": [], "conflicts": [], "to_merge": [], "preserved": [],
                },
            },
        )

        output = format_report(manifest, report, "owner/repo")
        assert "[+]" in output
        assert "new-hook.js" in output
        assert "WILL ADD" in output

    def test_up_to_date_shown(self):
        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": "~/.claude/hooks/",
                "merge_strategy": "skip_existing",
                "items": {
                    "a.js": make_hook_item("a"),
                    "b.js": make_hook_item("b"),
                },
            },
        })

        report = _build_report(
            up_to_date=[
                {"category": "hooks", "item_path": "a.js", "meta": {}},
                {"category": "hooks", "item_path": "b.js", "meta": {}},
            ],
            categories={
                "hooks": {
                    "to_add": [],
                    "up_to_date": [{"item_path": "a.js"}, {"item_path": "b.js"}],
                    "conflicts": [], "to_merge": [], "preserved": [],
                },
            },
        )

        output = format_report(manifest, report, "owner/repo")
        assert "UP TO DATE: 2 items" in output

    def test_conflicts_shown(self):
        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": "~/.claude/hooks/",
                "merge_strategy": "skip_existing",
                "items": {"custom.js": make_hook_item("custom")},
            },
        })

        report = _build_report(
            conflicts=[{"category": "hooks", "item_path": "custom.js", "meta": {}}],
            categories={
                "hooks": {
                    "to_add": [],
                    "up_to_date": [],
                    "conflicts": [{"item_path": "custom.js", "meta": {}}],
                    "to_merge": [], "preserved": [],
                },
            },
        )

        output = format_report(manifest, report, "owner/repo")
        assert "[!]" in output
        assert "custom.js" in output
        assert "CONFLICTS" in output

    def test_merge_items_shown(self):
        manifest = make_manifest({
            "mcp": {
                "path": "mcp/",
                "target": None,
                "merge_strategy": "merge_entries",
                "items": {"servers.yaml": {"checksum": "sha256:x", "id": "servers"}},
            },
        })

        report = _build_report(
            to_merge=[{"category": "mcp", "item_path": "servers.yaml", "meta": {}}],
            categories={
                "mcp": {
                    "to_add": [], "up_to_date": [], "conflicts": [],
                    "to_merge": [{"item_path": "servers.yaml", "meta": {}}],
                    "preserved": [],
                },
            },
        )

        output = format_report(manifest, report, "owner/repo")
        assert "[~]" in output
        assert "WILL MERGE" in output

    def test_preserved_items_shown(self):
        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": "~/.claude/hooks/",
                "merge_strategy": "skip_existing",
                "items": {},
            },
        })

        report = _build_report(
            preserved=[{"category": "hooks", "item_path": "my-hook.js"}],
            categories={
                "hooks": {
                    "to_add": [], "up_to_date": [], "conflicts": [], "to_merge": [],
                    "preserved": ["my-hook.js"],
                },
            },
        )

        output = format_report(manifest, report, "owner/repo")
        assert "[i]" in output
        assert "YOUR EXISTING" in output
        assert "my-hook.js" in output

    def test_no_items_message(self):
        manifest = make_manifest({
            "empty-cat": {
                "path": "empty/",
                "target": "~/.claude/empty/",
                "merge_strategy": "skip_existing",
                "items": {},
            },
        })

        report = _build_report(
            categories={
                "empty-cat": {
                    "to_add": [], "up_to_date": [], "conflicts": [], "to_merge": [], "preserved": [],
                },
            },
        )

        output = format_report(manifest, report, "owner/repo")
        assert "(no items)" in output


class TestSummaryLine:
    """Summary at the bottom of the report."""

    def test_summary_counts(self):
        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": "~/.claude/hooks/",
                "merge_strategy": "skip_existing",
                "items": {
                    "a.js": make_hook_item("a"),
                    "b.js": make_hook_item("b"),
                    "c.js": make_hook_item("c"),
                },
            },
        })

        report = _build_report(
            to_add=[
                {"category": "hooks", "item_path": "a.js", "meta": {}},
            ],
            up_to_date=[
                {"category": "hooks", "item_path": "b.js", "meta": {}},
            ],
            conflicts=[
                {"category": "hooks", "item_path": "c.js", "meta": {}},
            ],
            preserved=[
                {"category": "hooks", "item_path": "user.js"},
            ],
            categories={
                "hooks": {
                    "to_add": [{"item_path": "a.js"}],
                    "up_to_date": [{"item_path": "b.js"}],
                    "conflicts": [{"item_path": "c.js"}],
                    "to_merge": [],
                    "preserved": ["user.js"],
                },
            },
        )

        output = format_report(manifest, report, "owner/repo")

        assert "SUMMARY:" in output
        assert "1 add" in output
        assert "1 up-to-date" in output
        assert "1 conflicts" in output
        assert "1 preserved" in output

    def test_uninstall_hint_shown(self):
        manifest = make_manifest({})
        report = _build_report()
        output = format_report(manifest, report, "owner/repo")
        assert "config uninstall owner/repo" in output


class TestConflictMessage:
    """Special message shown when conflicts > 0."""

    def test_conflict_warning_when_conflicts_exist(self):
        manifest = make_manifest({
            "hooks": {
                "path": "hooks/", "target": "~/.claude/hooks/",
                "merge_strategy": "skip_existing",
                "items": {"x.js": make_hook_item("x")},
            },
        })
        report = _build_report(
            conflicts=[{"item_path": "x.js", "meta": {}}],
            categories={"hooks": {"to_add": [], "up_to_date": [], "conflicts": [{"item_path": "x.js"}], "to_merge": [], "preserved": []}},
        )

        output = format_report(manifest, report, "owner/repo")
        assert "SKIPPED" in output
        assert "config review" in output

    def test_no_conflict_warning_when_zero(self):
        manifest = make_manifest({
            "hooks": {
                "path": "hooks/", "target": "~/.claude/hooks/",
                "merge_strategy": "skip_existing",
                "items": {"x.js": make_hook_item("x")},
            },
        })
        report = _build_report(
            to_add=[{"item_path": "x.js", "meta": {}}],
            categories={"hooks": {"to_add": [{"item_path": "x.js"}], "up_to_date": [], "conflicts": [], "to_merge": [], "preserved": []}},
        )

        output = format_report(manifest, report, "owner/repo")
        # Should NOT contain the SKIPPED warning
        assert "Conflicts will be SKIPPED" not in output


class TestExistingSystemsInReport:
    """Existing hook systems detected are shown in the hooks section."""

    def test_existing_systems_displayed(self):
        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": "~/.claude/hooks/",
                "merge_strategy": "skip_existing",
                "items": {},
            },
        })

        report = _build_report(
            existing_systems=[
                {"event": "UserPromptSubmit", "filename": "gsd-gate.js", "matcher": "*", "command": "node gsd-gate.js"},
                {"event": "PostToolUse", "filename": "auto-gsd.js", "matcher": "*", "command": "node auto-gsd.js"},
            ],
            categories={
                "hooks": {"to_add": [], "up_to_date": [], "conflicts": [], "to_merge": [], "preserved": []},
            },
        )

        output = format_report(manifest, report, "owner/repo")
        assert "gsd-gate.js" in output
        assert "auto-gsd.js" in output
        assert "YOUR EXISTING" in output


class TestReportTitle:
    """Report header shows repo name and version."""

    def test_title_includes_repo_and_version(self):
        manifest = make_manifest({})
        manifest["version"] = "2.3.1"
        report = _build_report()

        output = format_report(manifest, report, "grobomo/claude-code-defaults")

        assert "grobomo/claude-code-defaults" in output
        assert "v2.3.1" in output

    def test_settings_entry_event_in_add_description(self):
        """Hook items with settings_entry show the event in the description."""
        manifest = make_manifest({
            "hooks": {
                "path": "hooks/",
                "target": "~/.claude/hooks/",
                "merge_strategy": "skip_existing",
                "items": {
                    "tool-reminder.js": make_hook_item("tool-reminder", event="PreToolUse"),
                },
            },
        })

        meta = make_hook_item("tool-reminder", event="PreToolUse")
        report = _build_report(
            to_add=[{"category": "hooks", "item_path": "tool-reminder.js", "meta": meta}],
            categories={
                "hooks": {
                    "to_add": [{"item_path": "tool-reminder.js", "meta": meta}],
                    "up_to_date": [], "conflicts": [], "to_merge": [], "preserved": [],
                },
            },
        )

        output = format_report(manifest, report, "owner/repo")
        assert "PreToolUse" in output
