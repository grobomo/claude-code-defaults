#!/usr/bin/env python3
"""
setup.py - Credential manager setup and verification.

Verifies the OS credential store is working and scans for plaintext tokens.
Safe to re-run at any time.

Usage:
    python ~/.claude/super-manager/credentials/setup.py
"""
import sys
import os
import platform
import json
from pathlib import Path

# Add parent for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.configuration_paths import CREDENTIALS_DIR, CREDENTIAL_REGISTRY, KNOWN_ENV_FILES, SECRET_PATTERNS


def check_keyring():
    """Verify keyring is installed and working."""
    print("Checking keyring...")
    try:
        import keyring
        backend = keyring.get_keyring()
        print("  Backend: {}".format(backend))
    except ImportError:
        print("  keyring not installed. Installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "keyring"])
        import keyring
        backend = keyring.get_keyring()
        print("  Backend: {}".format(backend))

    # Verify the backend is appropriate for the platform
    backend_name = type(backend).__name__
    system = platform.system()
    if system == "Windows" and "WinVault" not in backend_name:
        print("  WARNING: Expected WinVaultKeyring, got {}".format(backend_name))
    elif system == "Darwin" and "macOS" not in backend_name and "Keychain" not in backend_name:
        print("  WARNING: Expected macOS Keychain, got {}".format(backend_name))
    else:
        print("  OK - appropriate backend for {}".format(system))

    return keyring


def test_credential_store(keyring):
    """Test write/read/delete roundtrip."""
    print("\nTesting credential store...")
    test_key = "setup-test"
    test_value = "credential-manager-setup-verify"

    try:
        keyring.set_password("claude-code", test_key, test_value)
        retrieved = keyring.get_password("claude-code", test_key)
        if retrieved == test_value:
            print("  OK - write/read roundtrip successful")
        else:
            print("  FAIL - read returned unexpected value")
            return False
        keyring.delete_password("claude-code", test_key)
        print("  OK - delete successful")
        return True
    except Exception as e:
        print("  FAIL - {}".format(e))
        return False


def ensure_registry():
    """Create credential-registry.json if missing."""
    print("\nChecking registry...")
    os.makedirs(CREDENTIALS_DIR, exist_ok=True)
    if not os.path.exists(CREDENTIAL_REGISTRY):
        with open(CREDENTIAL_REGISTRY, "w") as f:
            json.dump({"credentials": []}, f, indent=2)
        print("  Created: {}".format(CREDENTIAL_REGISTRY))
    else:
        with open(CREDENTIAL_REGISTRY) as f:
            data = json.load(f)
        count = len(data.get("credentials", []))
        print("  Exists: {} credentials registered".format(count))


def scan_env_files():
    """Scan known .env files for plaintext tokens."""
    print("\nScanning .env files for plaintext tokens...")
    findings = []
    secure = []

    for service, env_path in KNOWN_ENV_FILES:
        if not os.path.exists(env_path):
            continue

        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"\'')

                # Check if this variable name looks like a secret
                is_secret = any(p.lower() in key.lower() for p in SECRET_PATTERNS)
                if not is_secret:
                    continue

                if value.startswith("credential:"):
                    secure.append("{}/{} -> credential store".format(service, key))
                else:
                    findings.append({
                        "service": service,
                        "variable": key,
                        "env_path": env_path,
                    })

    if secure:
        print("\n  Secure (credential store):")
        for s in secure:
            print("    [OK] {}".format(s))

    if findings:
        print("\n  PLAINTEXT tokens found:")
        for f in findings:
            print("    [WARN] {}/{} in {}".format(f["service"], f["variable"], f["env_path"]))
        print("\n  To migrate, run:")
        # Group by env_path
        seen = set()
        for f in findings:
            cmd_key = (f["env_path"], f["service"])
            if cmd_key not in seen:
                seen.add(cmd_key)
                print('    python super_manager.py credentials migrate "{}" {}'.format(
                    f["env_path"], f["service"]))
    elif not secure:
        print("  No .env files found at known locations")
    else:
        print("\n  All secrets are using credential store!")

    return findings


def install_slash_command():
    """Install /cred slash command for Claude Code."""
    print("\nInstalling /cred command...")
    commands_dir = os.path.join(Path.home(), ".claude", "commands")
    os.makedirs(commands_dir, exist_ok=True)
    cmd_path = os.path.join(commands_dir, "cred.md")

    cmd_content = """---
name: cred
description: "Credential manager - store, list, verify, audit, migrate secrets in OS credential store"
---

Credential manager command. Run the appropriate super-manager credentials subcommand based on the user's arguments: `$ARGUMENTS`

## Argument Routing

| User Types | Action |
|------------|--------|
| `/cred` (no args) | Run `python ~/.claude/super-manager/super_manager.py credentials list` and show stored credential names |
| `/cred list` | Run `python ~/.claude/super-manager/super_manager.py credentials list` |
| `/cred store SERVICE/KEY` | Tell user to run interactively: `python ~/.claude/super-manager/super_manager.py credentials store SERVICE/KEY` (requires hidden input - Claude cannot handle this) |
| `/cred store SERVICE/KEY --clipboard` | Tell user to copy the value to clipboard first, then run: `python ~/.claude/super-manager/super_manager.py credentials store SERVICE/KEY --clipboard` |
| `/cred verify` | Run `python ~/.claude/super-manager/super_manager.py credentials verify` |
| `/cred audit` | Run `python ~/.claude/super-manager/super_manager.py credentials audit` to find plaintext tokens in .env files |
| `/cred migrate PATH SERVICE` | Run `python ~/.claude/super-manager/super_manager.py credentials migrate "PATH" SERVICE` |
| `/cred setup` | Run `python ~/.claude/super-manager/credentials/setup.py` |

## Rules

- **NEVER output credential values** - only show key names
- **NEVER read .env files** - they may contain secrets
- For `store` commands, the user must run interactively (hidden input required)
- For everything else, execute the command directly via Bash tool
"""

    with open(cmd_path, "w") as f:
        f.write(cmd_content)
    print("  Installed: {} -> /cred".format(cmd_path))


def main():
    print("=" * 50)
    print("  Credential Manager Setup")
    print("=" * 50)
    print()

    kr = check_keyring()
    ok = test_credential_store(kr)
    if not ok:
        print("\nFAILED: Credential store not working. Cannot proceed.")
        sys.exit(1)

    ensure_registry()
    install_slash_command()
    findings = scan_env_files()

    print("\n" + "=" * 50)
    if findings:
        print("  Setup complete. {} plaintext tokens need migration.".format(len(findings)))
    else:
        print("  Setup complete. Credential store is ready.")
    print("  Slash command: /cred")
    print("=" * 50)


if __name__ == "__main__":
    main()
