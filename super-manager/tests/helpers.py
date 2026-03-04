"""
Shared test helpers for config_sync test suite.

Helper functions and constants used by test modules. This module
is importable (unlike conftest.py which pytest auto-loads).
"""
import json
import os
import sys

# Add super-manager to path so `from commands.config_sync import ...` works
SUPER_MANAGER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SUPER_MANAGER_DIR not in sys.path:
    sys.path.insert(0, SUPER_MANAGER_DIR)


def make_manifest(categories=None, version="1.0.0"):
    """Build a manifest dict with sensible defaults."""
    return {
        "version": version,
        "updated": "2026-02-22T00:00:00Z",
        "categories": categories or {},
    }


def make_hook_item(item_id, checksum="sha256:abc123", event="UserPromptSubmit",
                   matcher="*", is_async=False, **extra):
    """Build a single hook item dict."""
    entry = {
        "checksum": checksum,
        "id": item_id,
        "settings_entry": {
            "event": event,
            "matcher": matcher,
            "async": is_async,
        },
    }
    entry.update(extra)
    return entry


def make_rule_item(item_id, checksum="sha256:def456", description="test rule"):
    return {
        "checksum": checksum,
        "id": item_id,
        "description": description,
    }


def make_skill_item(item_id, checksum="sha256:ghi789", description="test skill"):
    return {
        "checksum": checksum,
        "id": item_id,
        "is_directory": True,
        "description": description,
    }


SAMPLE_MANIFEST = make_manifest({
    "hooks": {
        "path": "hooks/",
        "target": "~/.claude/hooks/",
        "merge_strategy": "skip_existing",
        "settings_registration": True,
        "items": {
            "tool-reminder.js": make_hook_item("tool-reminder"),
        },
    },
    "rules": {
        "path": "rules/",
        "target": "~/.claude/rules/",
        "merge_strategy": "skip_existing",
        "items": {
            "UserPromptSubmit/background-tasks.md": make_rule_item("background-tasks"),
        },
    },
    "skills": {
        "path": "skills/",
        "target": "~/.claude/skills/",
        "merge_strategy": "skip_existing",
        "items": {
            "super-manager/": make_skill_item("super-manager"),
        },
    },
})


def write_manifest(repo_dir, manifest):
    """Write manifest.json into a repo directory."""
    path = os.path.join(repo_dir, "manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return path
