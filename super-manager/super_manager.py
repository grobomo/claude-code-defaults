"""
super_manager.py - Unified CLI for managing all Claude Code configuration.

5 sub-managers: hooks, skills, mcp-servers, rules, credentials
3 orchestration commands: status, doctor, report
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.logger import create_logger
from shared.output_formatter import item_list

log = create_logger("super-manager")


def _get_manager(name):
    mapping = {
        "hooks": "managers.hook_manager",
        "skills": "managers.skill_manager",
        "mcp": "managers.mcp_server_manager",
        "rules": "managers.rule_manager",
        "credentials": "managers.credential_manager",
    }
    module_path = mapping.get(name)
    if not module_path:
        print(f"Unknown manager: {name}")
        sys.exit(1)
    return __import__(module_path, fromlist=["list_all"])


def _get_flag(args, flag, default=None):
    try:
        idx = args.index(flag)
        return args[idx + 1]
    except (ValueError, IndexError):
        return default


def cmd_status(args):
    from commands.show_status import run
    verbose = "--verbose" in args or "-v" in args
    run(verbose=verbose)


def cmd_doctor(args):
    from commands.run_doctor import run
    auto_fix = "--fix" in args
    run(auto_fix=auto_fix)


def cmd_report(args):
    from commands.generate_report import run
    run()


def cmd_duplicates(args):
    from commands.detect_duplicates import run, compare_projects
    verbose = "--verbose" in args or "-v" in args
    compare_paths = None
    if "--compare" in args:
        idx = args.index("--compare")
        if idx + 2 < len(args):
            compare_paths = [args[idx + 1], args[idx + 2]]
    run(verbose=verbose, compare_paths=compare_paths)


def cmd_analyze(args):
    from commands.analyze_effectiveness import run
    session = None
    if "--session" in args:
        idx = args.index("--session")
        if idx + 1 < len(args):
            session = args[idx + 1]
    verbose = "--verbose" in args or "-v" in args
    diagram = "--diagram" in args
    code = run(session_path=session, verbose=verbose, diagram=diagram)
    if "--open" in args:
        import subprocess
        from shared.configuration_paths import ANALYSIS_REPORT
        subprocess.Popen(["start", "", ANALYSIS_REPORT], shell=True)
    sys.exit(code)


def cmd_discover(args):
    from commands.discover import run
    report = "--report" in args
    run(report_only=report)


def cmd_config(args):
    from commands.config_sync import (
        do_add_repo, do_export, do_import, do_remove_repo,
        do_repos, do_restore, do_review, do_status, do_uninstall,
    )
    if not args:
        print("Config Sync - Import/export configuration from GitHub repos")
        print()
        print("  config import <owner/repo>      First-time install from repo")
        print("  config import                   Update from all registered repos")
        print("  config import --headless        Auto-approve ALL including conflicts")
        print("  config import --headless-safe   Auto-approve, skip conflicts")
        print("  config export <owner/repo>      Push local config to a repo")
        print("  config uninstall <owner/repo>   Remove repo's items, restore originals")
        print("  config uninstall --all          Remove everything, full restore")
        print("  config add-repo <owner/repo>    Register a config repo source")
        print("  config remove-repo <owner/repo> Unregister (archive, not delete)")
        print("  config repos                    List registered config repos")
        print("  config review                   Review pending conflicts")
        print("  config status                   What's installed, from which repos")
        print("  config restore <backup-id>      Restore to specific backup")
        print("  config restore --list           List available backups")
        return

    action = args[0]
    rest = args[1:]

    if action in ("--help", "-h", "help"):
        cmd_config([])  # show help
        return
    elif action == "import":
        repo = rest[0] if rest and not rest[0].startswith("-") else None
        headless = "--headless" in rest
        headless_safe = "--headless-safe" in rest
        do_import(repo, headless=headless, headless_safe=headless_safe)
    elif action == "export":
        if not rest:
            print("Usage: config export <owner/repo>")
            sys.exit(1)
        do_export(rest[0])
    elif action == "uninstall":
        if "--all" in rest:
            do_uninstall(uninstall_all=True)
        elif rest:
            do_uninstall(rest[0])
        else:
            print("Usage: config uninstall <owner/repo> or --all")
    elif action == "add-repo":
        if not rest:
            print("Usage: config add-repo <owner/repo>")
            sys.exit(1)
        do_add_repo(rest[0])
    elif action == "remove-repo":
        if not rest:
            print("Usage: config remove-repo <owner/repo>")
            sys.exit(1)
        do_remove_repo(rest[0])
    elif action == "repos":
        do_repos()
    elif action == "review":
        do_review()
    elif action == "status":
        do_status()
    elif action == "restore":
        list_mode = "--list" in rest
        backup_id = next((r for r in rest if not r.startswith("-")), None)
        do_restore(backup_id=backup_id, list_backups=list_mode)
    else:
        print(f"Unknown config action: {action}")
        sys.exit(1)


def cmd_manager_action(manager_name, action, args):
    mgr = _get_manager(manager_name)

    if action == "list":
        result = mgr.list_all()
        items = result.get("items", [])
        summary = result.get("summary", "")
        print()
        print(f"{manager_name.title()}: {summary}")
        print()
        if items:
            skip = {"command", "file_exists", "in_settings", "in_registry",
                    "skill_path", "file_path", "has_content", "on_disk", "keywords"}
            cols = [(k, k.replace("_", " ").title()) for k in items[0].keys() if k not in skip][:5]
            print(item_list(items, cols))
        print()

    elif action == "add":
        _do_add(manager_name, mgr, args)

    elif action == "remove":
        name = args[0] if args else None
        if not name:
            print(f"Usage: {manager_name} remove <name>")
            sys.exit(1)
        result = mgr.remove_item(name)
        print(result.get("message", "Done"))

    elif action == "enable":
        name = args[0] if args else None
        if not name:
            print(f"Usage: {manager_name} enable <name>")
            sys.exit(1)
        result = mgr.enable_item(name)
        print(result.get("message", "Done"))

    elif action == "disable":
        name = args[0] if args else None
        if not name:
            print(f"Usage: {manager_name} disable <name>")
            sys.exit(1)
        result = mgr.disable_item(name)
        print(result.get("message", "Done"))

    elif action == "verify":
        result = mgr.verify_all()
        healthy = result.get("healthy", [])
        issues = result.get("issues", [])
        print()
        print(f"{manager_name.title()} Verification")
        print(f"Healthy: {len(healthy)}, Issues: {len(issues)}")
        for issue in issues:
            item_name = issue.get("item", "?")
            problem = issue.get("problem", "?")
            print(f"  [ISSUE] {item_name}: {problem}")
        if not issues:
            print("  All items healthy")
        print()

    elif action == "match" and manager_name == "rules":
        prompt = " ".join(args) if args else ""
        if not prompt:
            print("Usage: rules match <prompt text>")
            sys.exit(1)
        matches = mgr.get_matching_rules(prompt)
        print()
        print("Matching rules:")
        for m in matches:
            mid = m.get("id", "?")
            mname = m.get("name", "?")
            print(f"  - {mid}: {mname}")
        if not matches:
            print("  (no matches)")
        print()

    elif action == "store" and manager_name == "credentials":
        key = args[0] if args else None
        if not key:
            print("Usage: credentials store <service/VARIABLE> [--clipboard|--stdin]")
            sys.exit(1)
        clipboard = "--clipboard" in args
        stdin = "--stdin" in args
        result = mgr.store_credential(key, clipboard=clipboard, stdin=stdin)
        print(result.get("message", "Done"))

    elif action == "migrate" and manager_name == "credentials":
        env_path = args[0] if args else None
        service = args[1] if len(args) > 1 else None
        if not env_path or not service:
            print("Usage: credentials migrate <env_path> <service>")
            sys.exit(1)
        result = mgr.migrate_env(env_path, service)
        print(result.get("message", "Done"))

    elif action == "audit" and manager_name == "credentials":
        result = mgr.audit_plaintext()
        findings = result.get("findings", [])
        print()
        print("Credential Audit")
        if findings:
            print(f"  {len(findings)} plaintext tokens found:")
            for f in findings:
                fpath = f.get("file", f.get("env_path", "?"))
                print(f"  [WARN] {f['service']}/{f['variable']} in {fpath}")
            print()
            print("  Migrate with:")
            seen = set()
            for f in findings:
                fpath = f.get("file", f.get("env_path", "?"))
                cmd_key = (fpath, f["service"])
                if cmd_key not in seen:
                    seen.add(cmd_key)
                    print(f'    python super_manager.py credentials migrate "{fpath}" {f["service"]}')
        else:
            print("  No plaintext tokens found. All secure!")
        print()

    else:
        print(f"Unknown action: {action}")
        print("Available: list, add, remove, enable, disable, verify")
        sys.exit(1)


def _do_add(manager_name, mgr, args):
    if manager_name == "hooks":
        name = args[0] if args else None
        event = _get_flag(args, "--event")
        command = _get_flag(args, "--command")
        desc = _get_flag(args, "--description", "")
        matcher = _get_flag(args, "--matcher", "*")
        if not all([name, event, command]):
            print("Usage: hooks add <name> --event <event> --command <cmd>")
            sys.exit(1)
        result = mgr.add_item(name, event, command, description=desc, matcher=matcher)
        print(result.get("message", "Done"))
    elif manager_name == "skills":
        name = args[0] if args else None
        path = _get_flag(args, "--path")
        desc = _get_flag(args, "--description", "")
        kw = _get_flag(args, "--keywords", "")
        keywords = [k.strip() for k in kw.split(",")] if kw else []
        if not all([name, path]):
            print("Usage: skills add <name> --path <path> [--keywords <kw1,kw2>]")
            sys.exit(1)
        result = mgr.add_item(name, path, description=desc, keywords=keywords)
        print(result.get("message", "Done"))
    elif manager_name == "rules":
        inst_id = args[0] if args else None
        name = _get_flag(args, "--name")
        kw = _get_flag(args, "--keywords", "")
        keywords = [k.strip() for k in kw.split(",")] if kw else []
        content = _get_flag(args, "--content", "")
        if not all([inst_id, name]):
            print("Usage: rules add <id> --name <name> --keywords <kw1,kw2>")
            sys.exit(1)
        result = mgr.add_item(inst_id, name, keywords, content)
        print(result.get("message", "Done"))
    else:
        print(f"Add not supported for {manager_name}")


def main():
    if len(sys.argv) < 2:
        print("Super Manager - Unified Claude Code Configuration")
        print()
        print("Orchestration:")
        print("  status [--verbose]    Show dashboard for all components")
        print("  doctor [--fix]        Find and fix configuration issues")
        print("  report                Generate markdown config report")
        print("  duplicates [--verbose] Find duplicate skills/projects")
        print("  duplicates --compare <path_a> <path_b>")
        print("  discover [--report]   Discover and auto-register all items")
        print("  analyze [--session <path>] [--verbose] [--diagram]")
        print("                        Analyze hook/rule effectiveness")
        print("  config <action>       Import/export config from GitHub repos")
        print()
        print("Sub-managers:")
        print("  hooks <action>        Manage Claude Code hooks")
        print("  skills <action>       Manage Claude Code skills")
        print("  rules <action>        Manage context-aware rules")
        print("  credentials <action>  Manage API tokens and secrets")
        print()
        print("MCP servers: Use mcpm MCP tools directly (list_servers, start, stop, reload)")
        print()
        print("Actions: list, add, remove, enable, disable, verify")
        print()
        print("Credential-specific actions:")
        print("  credentials store <service/KEY> [--clipboard|--stdin]")
        print("  credentials migrate <env_path> <service>")
        print("  credentials audit")
        sys.exit(0)

    command = sys.argv[1]
    rest = sys.argv[2:]

    if command == "status":
        cmd_status(rest)
    elif command == "doctor":
        cmd_doctor(rest)
    elif command == "report":
        cmd_report(rest)
    elif command == "duplicates":
        cmd_duplicates(rest)
    elif command == "discover":
        cmd_discover(rest)
    elif command == "analyze":
        cmd_analyze(rest)
    elif command == "config":
        cmd_config(rest)
    elif command == "mcp":
        print("MCP servers are managed by mcpm directly.")
        print("Use the mcpm MCP tools: list_servers, start, stop, reload, add")
        sys.exit(0)
    elif command in ("hooks", "skills", "rules", "credentials"):
        if not rest:
            print(f"Usage: super_manager.py {command} <action>")
            print("Actions: list, add, remove, enable, disable, verify")
            sys.exit(1)
        action = rest[0]
        action_args = rest[1:]
        cmd_manager_action(command, action, action_args)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
