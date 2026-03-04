"""
Integration test - Full config import/export/uninstall flow using REAL staging repo.
"""
import json, os, shutil, sys, time
import pytest

SUPER_MANAGER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SUPER_MANAGER_DIR not in sys.path:
    sys.path.insert(0, SUPER_MANAGER_DIR)

STAGING_REPO = os.path.join(SUPER_MANAGER_DIR, "config", "staging", "claude-code-defaults")
STAGING_MANIFEST = os.path.join(STAGING_REPO, "manifest.json")

pytestmark = pytest.mark.skipif(
    not os.path.isfile(STAGING_MANIFEST),
    reason="Staging repo not found at " + STAGING_MANIFEST,
)

from commands.config_sync import (
    analyze_conflicts, compute_dir_checksum, compute_file_checksum,
    create_config_backup, format_report, install_category,
    list_config_backups, load_installed, load_pending, load_repos,
    parse_manifest, record_installed, restore_config_backup,
    save_installed, save_pending, save_repos, uninstall_category,
    validate_manifest, verify_config_state, _register_repo, _repo_slug,
)
from helpers import make_hook_item, make_manifest, write_manifest


@pytest.fixture
def staging_manifest():
    return parse_manifest(STAGING_MANIFEST)


@pytest.fixture
def staging_env(tmp_path, monkeypatch, staging_manifest):
    import shared.configuration_paths as cp
    import commands.config_sync as cs

    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "hooks").mkdir()
    (claude / "skills").mkdir()
    (claude / "rules" / "UserPromptSubmit").mkdir(parents=True)
    (claude / "rules" / "Stop").mkdir(parents=True)
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

    mapping = {
        "CLAUDE_DIR": str(claude),
        "HOOKS_DIR": str(claude / "hooks"),
        "GLOBAL_SKILLS_DIR": str(claude / "skills"),
        "RULES_DIR": str(claude / "rules"),
        "SETTINGS_JSON": str(claude / "settings.json"),
        "CONFIG_DIR": str(config),
        "CONFIG_REPOS_DIR": str(config / "repos"),
        "CONFIG_BACKUPS_DIR": str(config / "backups"),
        "CONFIG_REPOS_JSON": str(config / "repos.json"),
        "CONFIG_INSTALLED_JSON": str(config / "installed.json"),
        "CONFIG_PENDING_JSON": str(config / "pending.json"),
        "LOGS_DIR": str(sm / "logs"),
    }
    for attr, value in mapping.items():
        monkeypatch.setattr(cp, attr, value)
        if hasattr(cs, attr):
            monkeypatch.setattr(cs, attr, value)

    manifest = json.loads(json.dumps(staging_manifest))
    target_map = {
        "~/.claude/hooks/": str(claude / "hooks"),
        "~/.claude/rules/": str(claude / "rules"),
        "~/.claude/skills/": str(claude / "skills"),
        "~/.claude/skills/credential-manager/": str(claude / "skills" / "credential-manager"),
        "~/.claude/": str(claude),
    }
    for cat_config in manifest["categories"].values():
        t = cat_config.get("target")
        if t and t in target_map:
            cat_config["target"] = target_map[t]

    return {"claude_dir": str(claude), "manifest": manifest, "repo_dir": STAGING_REPO,
            "targets": target_map, "mapping": mapping}


def _count_manifest_items(manifest):
    return sum(len(cc.get("items", {})) for cc in manifest.get("categories", {}).values())


class TestFreshImport:
    def test_all_items_to_add(self, staging_env):
        manifest = staging_env["manifest"]
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        total = _count_manifest_items(manifest)
        addable = len(report.to_add) + len(report.to_merge)
        assert addable == total
        assert len(report.conflicts) == 0
        assert len(report.up_to_date) == 0

    def test_every_category_present(self, staging_env):
        manifest = staging_env["manifest"]
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        for cat_name in manifest["categories"]:
            assert cat_name in report.categories

    def test_install_all_categories(self, staging_env):
        manifest = staging_env["manifest"]
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        all_changes = []
        for cat_name, cat_config in manifest["categories"].items():
            changes = install_category(cat_name, cat_config, staging_env["repo_dir"],
                                       report.categories.get(cat_name, {}))
            all_changes.extend(changes)
        added = sum(1 for c in all_changes if c.get("type") == "added")
        assert added > 0
        hooks_dir = os.path.join(staging_env["claude_dir"], "hooks")
        hook_files = [f for f in os.listdir(hooks_dir) if f.endswith(".js")]
        for hf in manifest["categories"]["hooks"]["items"]:
            assert hf in hook_files
        skills_dir = os.path.join(staging_env["claude_dir"], "skills")
        for item_path in manifest["categories"]["skills"]["items"]:
            assert os.path.isdir(os.path.join(skills_dir, item_path.rstrip("/")))

    def test_hooks_registered_in_settings(self, staging_env):
        manifest = staging_env["manifest"]
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        hooks_config = manifest["categories"]["hooks"]
        install_category("hooks", hooks_config, staging_env["repo_dir"],
                         report.categories.get("hooks", {}))
        with open(os.path.join(staging_env["claude_dir"], "settings.json"), "r",
                  encoding="utf-8") as f:
            settings = json.load(f)
        assert "hooks" in settings
        all_cmds = []
        for event, groups in settings["hooks"].items():
            for group in groups:
                for h in group.get("hooks", []):
                    all_cmds.append(h.get("command", ""))
        for filename, meta in hooks_config["items"].items():
            if meta.get("settings_entry"):
                assert any(filename in cmd for cmd in all_cmds)

    def test_report_format_valid(self, staging_env):
        manifest = staging_env["manifest"]
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        output = format_report(manifest, report, "grobomo/claude-code-defaults")
        assert "CONFIG IMPORT:" in output
        assert "SUMMARY:" in output
        for cat_name in manifest["categories"]:
            assert cat_name.upper() in output


def _custom_content():
    """Return custom hook content for conflict tests."""
    return "// custom" + chr(10)


def _precious_content():
    return "// precious" + chr(10)


def _user_custom_content():
    return "// user custom" + chr(10)


class TestConflictDetection:
    def test_pre_existing_hook(self, staging_env):
        manifest = staging_env["manifest"]
        hooks_dir = os.path.join(staging_env["claude_dir"], "hooks")
        first_hook = list(manifest["categories"]["hooks"]["items"].keys())[0]
        with open(os.path.join(hooks_dir, first_hook), "w", encoding="utf-8") as f:
            f.write(_custom_content())
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        assert first_hook in [c["item_path"] for c in report.conflicts]

    def test_pre_existing_skill_dir(self, staging_env):
        manifest = staging_env["manifest"]
        skills_dir = os.path.join(staging_env["claude_dir"], "skills")
        first_skill = list(manifest["categories"]["skills"]["items"].keys())[0]
        skill_path = os.path.join(skills_dir, first_skill.rstrip("/"))
        os.makedirs(skill_path, exist_ok=True)
        with open(os.path.join(skill_path, "CUSTOM.md"), "w", encoding="utf-8") as f:
            f.write("# Custom" + chr(10))
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        assert first_skill in [c["item_path"] for c in report.conflicts]

    def test_matching_file_up_to_date(self, staging_env):
        manifest = staging_env["manifest"]
        hooks_dir = os.path.join(staging_env["claude_dir"], "hooks")
        first_hook = list(manifest["categories"]["hooks"]["items"].keys())[0]
        shutil.copy2(os.path.join(staging_env["repo_dir"], "hooks", first_hook),
                     os.path.join(hooks_dir, first_hook))
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        assert first_hook in [u["item_path"] for u in report.up_to_date]

    def test_mixed_state(self, staging_env):
        manifest = staging_env["manifest"]
        hooks_dir = os.path.join(staging_env["claude_dir"], "hooks")
        hooks_items = list(manifest["categories"]["hooks"]["items"].keys())
        if len(hooks_items) >= 2:
            shutil.copy2(os.path.join(staging_env["repo_dir"], "hooks", hooks_items[0]),
                         os.path.join(hooks_dir, hooks_items[0]))
            with open(os.path.join(hooks_dir, hooks_items[1]), "w", encoding="utf-8") as f:
                f.write(_custom_content())
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        assert len(report.up_to_date) >= 1
        assert len(report.conflicts) >= 1
        assert len(report.to_add) >= 1


class TestHeadlessMode:
    def test_overwrites_conflicts(self, staging_env):
        manifest = staging_env["manifest"]
        hooks_dir = os.path.join(staging_env["claude_dir"], "hooks")
        first_hook = list(manifest["categories"]["hooks"]["items"].keys())[0]
        custom_path = os.path.join(hooks_dir, first_hook)
        with open(custom_path, "w", encoding="utf-8") as f:
            f.write(_user_custom_content())
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        changes = install_category("hooks", manifest["categories"]["hooks"],
                                   staging_env["repo_dir"],
                                   report.categories.get("hooks", {}), headless=True)
        with open(custom_path, "r", encoding="utf-8") as f:
            content = f.read()
        with open(os.path.join(staging_env["repo_dir"], "hooks", first_hook), "r",
                  encoding="utf-8") as f:
            repo_content = f.read()
        assert content == repo_content
        assert any(c.get("type") == "replaced" for c in changes)

    def test_installs_all(self, staging_env):
        manifest = staging_env["manifest"]
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        all_changes = []
        for cat_name, cat_config in manifest["categories"].items():
            changes = install_category(cat_name, cat_config, staging_env["repo_dir"],
                                       report.categories.get(cat_name, {}), headless=True)
            all_changes.extend(changes)
        assert sum(1 for c in all_changes if c.get("type") == "added") > 0


class TestHeadlessSafeMode:
    def test_skips_conflicts(self, staging_env):
        manifest = staging_env["manifest"]
        hooks_dir = os.path.join(staging_env["claude_dir"], "hooks")
        first_hook = list(manifest["categories"]["hooks"]["items"].keys())[0]
        custom_path = os.path.join(hooks_dir, first_hook)
        with open(custom_path, "w", encoding="utf-8") as f:
            f.write(_precious_content())
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        changes = install_category("hooks", manifest["categories"]["hooks"],
                                   staging_env["repo_dir"],
                                   report.categories.get("hooks", {}), headless_safe=True)
        with open(custom_path, "r", encoding="utf-8") as f:
            assert f.read() == _precious_content()
        assert not any(c.get("type") == "replaced" for c in changes)

    def test_installs_new_items(self, staging_env):
        manifest = staging_env["manifest"]
        hooks_dir = os.path.join(staging_env["claude_dir"], "hooks")
        hook_items = list(manifest["categories"]["hooks"]["items"].keys())
        with open(os.path.join(hooks_dir, hook_items[0]), "w", encoding="utf-8") as f:
            f.write(_custom_content())
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        changes = install_category("hooks", manifest["categories"]["hooks"],
                                   staging_env["repo_dir"],
                                   report.categories.get("hooks", {}), headless_safe=True)
        added = [c for c in changes if c.get("type") == "added"]
        assert len(added) >= len(hook_items) - 1


class TestUninstall:
    def _install_all(self, staging_env):
        manifest = staging_env["manifest"]
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        all_changes = []
        for cat_name, cat_config in manifest["categories"].items():
            changes = install_category(cat_name, cat_config, staging_env["repo_dir"],
                                       report.categories.get(cat_name, {}))
            all_changes.extend(changes)
        record_installed("grobomo/claude-code-defaults", manifest, all_changes)

    def test_archives_hooks(self, staging_env):
        self._install_all(staging_env)
        manifest = staging_env["manifest"]
        installed = load_installed()
        slug = _repo_slug("grobomo/claude-code-defaults")
        cat_items = installed[slug]["categories"].get("hooks", {})
        actions = uninstall_category("hooks", manifest["categories"]["hooks"], cat_items)
        assert any(a["action"] == "archived" for a in actions)
        hooks_dir = os.path.join(staging_env["claude_dir"], "hooks")
        assert not [f for f in os.listdir(hooks_dir) if f.endswith(".js")]

    def test_removes_settings_entries(self, staging_env):
        self._install_all(staging_env)
        manifest = staging_env["manifest"]
        installed = load_installed()
        slug = _repo_slug("grobomo/claude-code-defaults")
        cat_items = installed[slug]["categories"].get("hooks", {})
        uninstall_category("hooks", manifest["categories"]["hooks"], cat_items)
        with open(os.path.join(staging_env["claude_dir"], "settings.json"), "r",
                  encoding="utf-8") as f:
            post = json.load(f)
        remaining = []
        for ev, groups in post.get("hooks", {}).items():
            for g in groups:
                for h in g.get("hooks", []):
                    remaining.append(h.get("command", ""))
        for fn in manifest["categories"]["hooks"]["items"]:
            assert not any(fn in cmd for cmd in remaining)

    def test_archives_skills(self, staging_env):
        self._install_all(staging_env)
        manifest = staging_env["manifest"]
        installed = load_installed()
        slug = _repo_slug("grobomo/claude-code-defaults")
        cat_items = installed[slug]["categories"].get("skills", {})
        actions = uninstall_category("skills", manifest["categories"]["skills"], cat_items)
        assert any(a["action"] == "archived" for a in actions)

    def test_installed_json_cleared(self, staging_env):
        self._install_all(staging_env)
        installed = load_installed()
        slug = _repo_slug("grobomo/claude-code-defaults")
        manifest = staging_env["manifest"]
        for cat_name, cat_config in manifest["categories"].items():
            cat_items = installed[slug]["categories"].get(cat_name, {})
            uninstall_category(cat_name, cat_config, cat_items)
        del installed[slug]
        save_installed(installed)
        assert slug not in load_installed()


class TestDynamicCategory:
    def test_unknown_category_in_manifest(self, staging_env, tmp_path):
        manifest = staging_env["manifest"]
        manifest["categories"]["custom-widgets"] = {
            "path": "custom-widgets/", "target": str(tmp_path / "widgets"),
            "merge_strategy": "skip_existing",
            "items": {"widget-a.conf": {"checksum": "sha256:custom123", "id": "widget-a"}},
        }
        (tmp_path / "widgets").mkdir()
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        assert "custom-widgets" in report.categories
        assert any(e.get("category") == "custom-widgets" for e in report.to_add)

    def test_unknown_category_install(self, staging_env, tmp_path):
        repo = tmp_path / "repo" / "gadgets"
        repo.mkdir(parents=True)
        (repo / "gadget.yaml").write_text("type: gadget", encoding="utf-8")
        target = tmp_path / "installed_gadgets"
        target.mkdir()
        cat_config = {
            "path": "gadgets/", "target": str(target),
            "merge_strategy": "skip_existing",
            "items": {"gadget.yaml": {"checksum": "sha256:g1", "id": "gadget"}},
        }
        changes = install_category("gadgets", cat_config, str(tmp_path / "repo"),
                                   {"conflicts": []})
        assert (target / "gadget.yaml").exists()
        assert changes[0]["type"] == "added"

    def test_validate_accepts_extra(self, staging_env):
        manifest = staging_env["manifest"]
        manifest["categories"]["extra"] = {
            "path": "extra/", "merge_strategy": "skip_existing", "items": {},
        }
        assert validate_manifest(manifest) == []


class TestExportRoundTrip:
    def test_preserves_content(self, staging_env, tmp_path):
        manifest = staging_env["manifest"]
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        hooks_config = manifest["categories"]["hooks"]
        install_category("hooks", hooks_config, staging_env["repo_dir"],
                         report.categories.get("hooks", {}))
        export_dir = tmp_path / "export" / "hooks"
        export_dir.mkdir(parents=True)
        hooks_dir = os.path.join(staging_env["claude_dir"], "hooks")
        for fn in hooks_config["items"]:
            src = os.path.join(hooks_dir, fn)
            if os.path.isfile(src):
                shutil.copy2(src, str(export_dir / fn))
        for fn in hooks_config["items"]:
            orig = os.path.join(staging_env["repo_dir"], "hooks", fn)
            exp = str(export_dir / fn)
            if os.path.isfile(orig):
                assert compute_file_checksum(orig) == compute_file_checksum(exp)

    def test_updates_checksums(self, staging_env, tmp_path):
        manifest = staging_env["manifest"]
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        hooks_config = manifest["categories"]["hooks"]
        install_category("hooks", hooks_config, staging_env["repo_dir"],
                         report.categories.get("hooks", {}))
        first_hook = list(hooks_config["items"].keys())[0]
        path = os.path.join(staging_env["claude_dir"], "hooks", first_hook)
        with open(path, "a", encoding="utf-8") as f:
            f.write("// modified")
        assert compute_file_checksum(path) != hooks_config["items"][first_hook]["checksum"]

    def test_skill_dir_round_trip(self, staging_env, tmp_path):
        manifest = staging_env["manifest"]
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        skills_config = manifest["categories"]["skills"]
        install_category("skills", skills_config, staging_env["repo_dir"],
                         report.categories.get("skills", {}))
        skills_dir = os.path.join(staging_env["claude_dir"], "skills")
        for item_path in skills_config["items"]:
            name = item_path.rstrip("/")
            installed_path = os.path.join(skills_dir, name)
            repo_path = os.path.join(staging_env["repo_dir"], "skills", name)
            if os.path.isdir(installed_path):
                assert compute_dir_checksum(installed_path) == compute_dir_checksum(repo_path)


class TestConfigCommands:
    def test_repos_empty(self, staging_env):
        assert load_repos() == []

    def test_register_repo(self, staging_env):
        _register_repo("grobomo/claude-code-defaults")
        repos = load_repos()
        assert len(repos) == 1
        assert repos[0]["owner_repo"] == "grobomo/claude-code-defaults"
        assert repos[0]["alias"] == "claude-code-defaults"

    def test_register_idempotent(self, staging_env):
        _register_repo("grobomo/claude-code-defaults")
        _register_repo("grobomo/claude-code-defaults")
        assert len(load_repos()) == 1

    def test_register_multiple(self, staging_env):
        _register_repo("grobomo/claude-code-defaults")
        _register_repo("other/repo")
        assert len(load_repos()) == 2

    def test_installed_empty(self, staging_env):
        assert load_installed() == {}

    def test_record_installed(self, staging_env):
        manifest = staging_env["manifest"]
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        all_changes = []
        for cat_name, cat_config in manifest["categories"].items():
            changes = install_category(cat_name, cat_config, staging_env["repo_dir"],
                                       report.categories.get(cat_name, {}))
            all_changes.extend(changes)
        record_installed("grobomo/claude-code-defaults", manifest, all_changes)
        installed = load_installed()
        slug = _repo_slug("grobomo/claude-code-defaults")
        assert slug in installed
        assert installed[slug]["version"] == manifest["version"]

    def test_pending_save_load(self, staging_env):
        save_pending([{"repo": "test", "category": "hooks",
                       "item_path": "x.js", "reason": "test"}])
        assert len(load_pending()) == 1
        save_pending([])
        assert len(load_pending()) == 0

    def test_slug_conversion(self, staging_env):
        assert _repo_slug("grobomo/claude-code-defaults") == "grobomo--claude-code-defaults"

    def test_verify_all_healthy(self, staging_env):
        manifest = staging_env["manifest"]
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        all_changes = []
        for cat_name, cat_config in manifest["categories"].items():
            changes = install_category(cat_name, cat_config, staging_env["repo_dir"],
                                       report.categories.get(cat_name, {}))
            all_changes.extend(changes)
        record_installed("grobomo/claude-code-defaults", manifest, all_changes)
        result = verify_config_state()
        assert len(result["issues"]) == 0
        assert len(result["healthy"]) > 0

    def test_verify_detects_missing(self, staging_env):
        manifest = staging_env["manifest"]
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        all_changes = []
        for cat_name, cat_config in manifest["categories"].items():
            changes = install_category(cat_name, cat_config, staging_env["repo_dir"],
                                       report.categories.get(cat_name, {}))
            all_changes.extend(changes)
        record_installed("grobomo/claude-code-defaults", manifest, all_changes)
        first_hook = list(manifest["categories"]["hooks"]["items"].keys())[0]
        hook_path = os.path.join(staging_env["claude_dir"], "hooks", first_hook)
        if os.path.isfile(hook_path):
            os.remove(hook_path)
        result = verify_config_state()
        assert len(result["issues"]) > 0


class TestBackupRestore:
    def test_backup_created(self, staging_env):
        backup_dir = create_config_backup("grobomo/claude-code-defaults")
        assert os.path.isdir(backup_dir)
        assert os.path.isfile(os.path.join(backup_dir, "restore.json"))
        assert os.path.isfile(os.path.join(backup_dir, "settings.json"))

    def test_backup_listed(self, staging_env):
        create_config_backup("grobomo/claude-code-defaults")
        backups = list_config_backups()
        assert len(backups) == 1
        assert backups[0]["repo"] == "grobomo/claude-code-defaults"

    def test_multiple_backups_sorted(self, staging_env):
        create_config_backup("repo-a")
        time.sleep(1.1)
        create_config_backup("repo-b")
        backups = list_config_backups()
        assert len(backups) == 2
        assert backups[0]["repo"] == "repo-b"

    def test_restore_reverts_settings(self, staging_env):
        settings_path = os.path.join(staging_env["claude_dir"], "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump({"version": "original"}, f)
        backup_dir = create_config_backup("grobomo/claude-code-defaults")
        backup_id = os.path.basename(backup_dir)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump({"version": "modified"}, f)
        restore_config_backup(backup_id)
        with open(settings_path, "r", encoding="utf-8") as f:
            assert json.load(f)["version"] == "original"

    def test_restore_archives_added(self, staging_env):
        backup_dir = create_config_backup("grobomo/claude-code-defaults")
        backup_id = os.path.basename(backup_dir)
        test_file = os.path.join(staging_env["claude_dir"], "hooks", "test-added.js")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("// added")
        restore_path = os.path.join(backup_dir, "restore.json")
        with open(restore_path, "r", encoding="utf-8") as f:
            rd = json.load(f)
        rd["changes"] = [{"type": "added", "path": test_file}]
        with open(restore_path, "w", encoding="utf-8") as f:
            json.dump(rd, f)
        result = restore_config_backup(backup_id)
        assert not os.path.isfile(test_file)
        assert len(result.get("archived", [])) == 1

    def test_restore_nonexistent(self, staging_env):
        assert "error" in restore_config_backup("nonexistent")


class TestFullLifecycle:
    def test_complete_lifecycle(self, staging_env):
        manifest = staging_env["manifest"]
        report = analyze_conflicts(manifest, staging_env["repo_dir"])
        counts = report.summary_counts()
        assert counts["conflicts"] == 0
        assert counts["add"] + counts["merge"] == _count_manifest_items(manifest)
        all_changes = []
        for cat_name, cat_config in manifest["categories"].items():
            changes = install_category(cat_name, cat_config, staging_env["repo_dir"],
                                       report.categories.get(cat_name, {}))
            all_changes.extend(changes)
        record_installed("grobomo/claude-code-defaults", manifest, all_changes)
        _register_repo("grobomo/claude-code-defaults")
        assert len(verify_config_state()["issues"]) == 0
        report2 = analyze_conflicts(manifest, staging_env["repo_dir"])
        assert len(report2.up_to_date) > 0
        assert len(report2.to_add) == 0
        installed = load_installed()
        slug = _repo_slug("grobomo/claude-code-defaults")
        for cat_name, cat_items in installed[slug]["categories"].items():
            cat_config = manifest["categories"].get(cat_name,
                         {"target": None, "path": cat_name + "/"})
            uninstall_category(cat_name, cat_config, cat_items)
        del installed[slug]
        save_installed(installed)
        assert slug not in load_installed()
        hooks_dir = os.path.join(staging_env["claude_dir"], "hooks")
        assert not [f for f in os.listdir(hooks_dir) if f.endswith(".js")]

    def test_install_uninstall_reinstall(self, staging_env):
        manifest = staging_env["manifest"]
        report1 = analyze_conflicts(manifest, staging_env["repo_dir"])
        changes1 = []
        for cn, cc in manifest["categories"].items():
            changes1.extend(install_category(cn, cc, staging_env["repo_dir"],
                            report1.categories.get(cn, {})))
        record_installed("grobomo/claude-code-defaults", manifest, changes1)
        installed = load_installed()
        slug = _repo_slug("grobomo/claude-code-defaults")
        for cn, ci in installed[slug]["categories"].items():
            uninstall_category(cn, manifest["categories"].get(cn,
                               {"target": None, "path": ""}), ci)
        del installed[slug]
        save_installed(installed)
        report2 = analyze_conflicts(manifest, staging_env["repo_dir"])
        assert len(report2.to_add) + len(report2.to_merge) > 0
        changes2 = []
        for cn, cc in manifest["categories"].items():
            changes2.extend(install_category(cn, cc, staging_env["repo_dir"],
                            report2.categories.get(cn, {})))
        record_installed("grobomo/claude-code-defaults", manifest, changes2)
        assert len(verify_config_state()["issues"]) == 0


class TestRealManifestValidation:
    def test_valid(self, staging_manifest):
        assert validate_manifest(staging_manifest) == []

    def test_six_categories(self, staging_manifest):
        expected = {"hooks", "rules", "skills", "credentials", "mcp", "claude-md"}
        assert set(staging_manifest["categories"].keys()) == expected

    def test_version_present(self, staging_manifest):
        assert staging_manifest.get("version")

    def test_checksums_present(self, staging_manifest):
        for cn, cc in staging_manifest["categories"].items():
            for ip, im in cc.get("items", {}).items():
                assert im.get("checksum", "").startswith("sha256:")

    def test_source_files_exist(self, staging_manifest):
        for cn, cc in staging_manifest["categories"].items():
            sp = cc.get("path", "")
            for ip, im in cc.get("items", {}).items():
                full = os.path.join(STAGING_REPO, sp, ip)
                if im.get("is_directory"):
                    assert os.path.isdir(full), f"Missing dir: {full}"
                else:
                    assert os.path.isfile(full), f"Missing file: {full}"

    def test_checksums_current(self, staging_manifest):
        mismatches = []
        for cn, cc in staging_manifest["categories"].items():
            sp = cc.get("path", "")
            for ip, im in cc.get("items", {}).items():
                full = os.path.join(STAGING_REPO, sp, ip)
                expected = im.get("checksum", "")
                if im.get("is_directory"):
                    actual = compute_dir_checksum(full)
                else:
                    actual = compute_file_checksum(full)
                if actual and actual != expected:
                    mismatches.append(f"{cn}/{ip}")
        assert mismatches == [], "Stale checksums: " + ", ".join(mismatches)
