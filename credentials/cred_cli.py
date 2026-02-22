"""
cred_cli.py - Standalone credential manager CLI.

Self-contained -- works without super-manager. Uses OS keyring directly.

Usage:
    python cred_cli.py list [SERVICE]
    python cred_cli.py store SERVICE/KEY
    python cred_cli.py verify
    python cred_cli.py audit [PATH_TO_ENV]
    python cred_cli.py migrate PATH_TO_ENV SERVICE
    python cred_cli.py securify DIRECTORY [--service NAME] [--dry-run]
"""
import sys
import os
import re
import json
import datetime
import platform

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SKILL_DIR, "credential-registry.json")
ARCHIVE_PATH = os.path.join(SKILL_DIR, "archived-credentials.jsonl")
KEYRING_SERVICE = "claude-code"
SECRET_PATTERNS = ["TOKEN", "KEY", "SECRET", "PASSWORD", "PASS", "AUTH"]

try:
    import keyring
except ImportError:
    print("ERROR: keyring not installed. Run: pip install keyring")
    sys.exit(1)


# --- Registry I/O ---

def read_registry():
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("credentials", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def write_registry(creds):
    data = {"credentials": creds}
    tmp = REGISTRY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, REGISTRY_PATH)


def now_iso():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Commands ---

def cmd_list(service_filter=None):
    creds = read_registry()
    if not creds:
        print("No credentials stored.")
        return

    for c in creds:
        if service_filter and c.get("service") != service_filter:
            continue
        key = c["key"]
        try:
            val = keyring.get_password(KEYRING_SERVICE, key)
            status = "[OK]" if val else "[MISSING]"
        except Exception:
            status = "[ERROR]"
        print(f"  {status} {key}  (added: {c.get('added', '?')})")

    services = set(c["service"] for c in creds)
    print(f"\n{len(creds)} credentials across {len(services)} services")


def cmd_store(key):
    if "/" not in key:
        print(f"ERROR: key must be SERVICE/VARIABLE, got: {key}")
        sys.exit(1)
    # Launch GUI
    gui_path = os.path.join(SKILL_DIR, "store_gui.py")
    if os.path.exists(gui_path):
        os.system(f'python "{gui_path}" "{key}"')
    else:
        print(f"ERROR: store_gui.py not found at {gui_path}")
        sys.exit(1)


def cmd_verify():
    creds = read_registry()
    healthy = []
    issues = []

    for c in creds:
        key = c["key"]
        try:
            val = keyring.get_password(KEYRING_SERVICE, key)
            if val:
                healthy.append(key)
            else:
                issues.append(f"  {key}: registered but not in OS keyring")
        except Exception as e:
            issues.append(f"  {key}: keyring error - {e}")

    print(f"Healthy: {len(healthy)}")
    if issues:
        print(f"Issues: {len(issues)}")
        for i in issues:
            print(i)
    else:
        print("No issues found.")


def cmd_audit(env_path=None):
    """Scan .env files for plaintext secrets."""
    env_files = []
    if env_path:
        env_files.append(("custom", env_path))
    else:
        # Scan common MCP locations
        projects = os.environ.get("MCP_DIR", os.path.expanduser("~/mcp"))
        if os.path.isdir(projects):
            for d in os.listdir(projects):
                env = os.path.join(projects, d, ".env")
                if os.path.isfile(env):
                    env_files.append((d, env))

    findings = 0
    for service, path in env_files:
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                m = re.match(r"^([A-Za-z_]\w*)=(.*)$", s)
                if not m:
                    continue
                var, val = m.group(1), m.group(2).strip().strip("'\"")
                if any(p in var.upper() for p in SECRET_PATTERNS):
                    if val and not val.startswith("credential:"):
                        print(f"  PLAINTEXT: {var} in {path}")
                        print(f"    Fix: python cred_cli.py migrate \"{path}\" {service}")
                        findings += 1

    print(f"\n{findings} plaintext secrets found across {len(env_files)} .env files")


def cmd_migrate(env_path, service):
    """Migrate plaintext secrets from .env to credential store."""
    if not os.path.isfile(env_path):
        print(f"ERROR: file not found: {env_path}")
        sys.exit(1)

    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    creds = read_registry()
    migrated = []
    new_lines = []

    for line in lines:
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            new_lines.append(line)
            continue

        m = re.match(r"^([A-Za-z_]\w*)=(.*)$", s)
        if not m:
            new_lines.append(line)
            continue

        var = m.group(1)
        val = m.group(2).strip().strip("'\"")

        if not any(p in var.upper() for p in SECRET_PATTERNS):
            new_lines.append(line)
            continue
        if val.startswith("credential:") or not val:
            new_lines.append(line)
            continue

        key = f"{service}/{var}"
        try:
            keyring.set_password(KEYRING_SERVICE, key, val)
        except Exception as e:
            print(f"  SKIP {var}: keyring error - {e}")
            new_lines.append(line)
            continue

        # Update registry
        existing = next((c for c in creds if c["key"] == key), None)
        if existing:
            existing["added"] = now_iso()
        else:
            creds.append({"key": key, "service": service, "variable": var, "added": now_iso()})

        new_lines.append(f"{var}=credential:{key}\n")
        migrated.append(key)
        print(f"  Migrated: {var} -> credential:{key}")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    write_registry(creds)
    print(f"\n{len(migrated)} secrets migrated from {os.path.basename(env_path)}")


# --- Main ---

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1]
    args = sys.argv[2:]

    if action == "list":
        cmd_list(args[0] if args else None)
    elif action == "store":
        if not args:
            print("Usage: cred_cli.py store SERVICE/KEY")
            sys.exit(1)
        cmd_store(args[0])
    elif action == "verify":
        cmd_verify()
    elif action == "audit":
        cmd_audit(args[0] if args else None)
    elif action == "migrate":
        if len(args) < 2:
            print("Usage: cred_cli.py migrate PATH_TO_ENV SERVICE")
            sys.exit(1)
        cmd_migrate(args[0], args[1])
    elif action == "securify":
        if not args:
            print("Usage: cred_cli.py securify DIRECTORY [--service NAME] [--dry-run]")
            sys.exit(1)
        from securify import securify
        directory = args[0]
        service = None
        dry_run = False
        i = 1
        while i < len(args):
            if args[i] in ("--service", "-s") and i + 1 < len(args):
                service = args[i + 1]
                i += 2
            elif args[i] in ("--dry-run", "-n"):
                dry_run = True
                i += 1
            else:
                i += 1
        securify(directory, service=service, dry_run=dry_run)
    else:
        print(f"Unknown command: {action}")
        print(__doc__)
        sys.exit(1)
