"""
Shared pytest fixtures for config_sync test suite.

All tests use tmp_path to avoid side effects on the real system.
The config_sync module's path constants are monkeypatched to point
at temp directories for each test.
"""
import json
import os
import sys

import pytest

# Add super-manager to path so `from commands.config_sync import ...` works
SUPER_MANAGER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SUPER_MANAGER_DIR not in sys.path:
    sys.path.insert(0, SUPER_MANAGER_DIR)

# Also add tests/ to path so helpers.py is importable
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)


@pytest.fixture
def fake_claude_dir(tmp_path):
    """
    Create a temporary ~/.claude structure and monkeypatch ALL module-level
    path constants to point into it.  Returns the tmp .claude dir path.
    """
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "hooks").mkdir()
    (claude / "skills").mkdir()
    (claude / "rules" / "UserPromptSubmit").mkdir(parents=True)
    (claude / "settings.json").write_text("{}", encoding="utf-8")
    (claude / "archive").mkdir()

    sm = claude / "super-manager"
    sm.mkdir()
    config = sm / "config"
    config.mkdir()
    (config / "repos").mkdir()
    (config / "backups").mkdir()
    (sm / "logs").mkdir()
    (sm / "registries").mkdir()

    return claude


@pytest.fixture
def patch_paths(fake_claude_dir, monkeypatch):
    """
    Monkeypatch all config_sync path constants to use the temp directory.
    Also patches the shared.configuration_paths module so the logger doesn't
    write to real dirs.
    """
    import shared.configuration_paths as cp
    import commands.config_sync as cs

    claude = str(fake_claude_dir)

    mapping = {
        "CLAUDE_DIR": claude,
        "HOOKS_DIR": os.path.join(claude, "hooks"),
        "GLOBAL_SKILLS_DIR": os.path.join(claude, "skills"),
        "RULES_DIR": os.path.join(claude, "rules"),
        "SETTINGS_JSON": os.path.join(claude, "settings.json"),
        "CONFIG_DIR": os.path.join(claude, "super-manager", "config"),
        "CONFIG_REPOS_DIR": os.path.join(claude, "super-manager", "config", "repos"),
        "CONFIG_BACKUPS_DIR": os.path.join(claude, "super-manager", "config", "backups"),
        "CONFIG_REPOS_JSON": os.path.join(claude, "super-manager", "config", "repos.json"),
        "CONFIG_INSTALLED_JSON": os.path.join(claude, "super-manager", "config", "installed.json"),
        "CONFIG_PENDING_JSON": os.path.join(claude, "super-manager", "config", "pending.json"),
        "LOGS_DIR": os.path.join(claude, "super-manager", "logs"),
    }

    for attr, value in mapping.items():
        monkeypatch.setattr(cp, attr, value)
        if hasattr(cs, attr):
            monkeypatch.setattr(cs, attr, value)

    return mapping


@pytest.fixture
def repo_dir(tmp_path):
    """
    Create a fake repo clone directory with manifest.json and source files.
    Returns path to the repo clone dir.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    # hooks/
    hooks = repo / "hooks"
    hooks.mkdir()
    (hooks / "tool-reminder.js").write_text("// tool reminder hook\nconsole.log('hello');", encoding="utf-8")

    # rules/
    instr = repo / "rules" / "UserPromptSubmit"
    instr.mkdir(parents=True)
    (instr / "background-tasks.md").write_text("# Background tasks\nDo stuff.", encoding="utf-8")

    # skills/
    skill = repo / "skills" / "super-manager"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Super Manager\nSkill doc.", encoding="utf-8")
    (skill / "main.py").write_text("print('hello')", encoding="utf-8")

    return str(repo)
