"""
smoke_credentials.py - Verify credential tooling and scan for plaintext secrets.

Checks:
  - cred_cli.py exists in ~/.claude/skills/credential-manager/
  - credential-registry.json is valid JSON at ~/.claude/super-manager/credentials/
  - Known .env files are scanned for plaintext tokens (TOKEN, KEY, SECRET, PASSWORD patterns)

Returns: {"healthy": [...], "issues": [{item, problem}]}
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.configuration_paths import (
    CREDENTIAL_REGISTRY,
    GLOBAL_SKILLS_DIR,
    KNOWN_ENV_FILES,
    SECRET_PATTERNS,
)


def _load_json(path, default=None):
    """Load a JSON file, returning default on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return default


def _scan_env_for_plaintext(env_path, service_name):
    """
    Scan a .env file for plaintext secret values.
    Returns list of issue dicts for any secret that is NOT using credential: prefix.
    """
    found = []
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (IOError, UnicodeDecodeError):
        return found

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Parse KEY=VALUE
        eq_idx = line.find("=")
        if eq_idx == -1:
            continue

        key = line[:eq_idx].strip()
        value = line[eq_idx + 1:].strip().strip('"').strip("'")

        # Check if key name matches secret patterns
        key_upper = key.upper()
        is_secret_key = any(pat in key_upper for pat in SECRET_PATTERNS)

        if not is_secret_key:
            continue

        # If value uses credential: prefix, it's properly secured
        if value.startswith("credential:"):
            continue

        # If value is empty, skip
        if not value:
            continue

        # Plaintext secret detected
        found.append({
            "item": f"{service_name}/{key}",
            "problem": f"Plaintext secret in {os.path.basename(env_path)} line {line_num} (use 'credential:' prefix instead)",
        })

    return found


def run():
    """Verify credential tooling and scan for plaintext secrets."""
    healthy = []
    issues = []

    # Check 1: cred_cli.py exists
    cred_cli_path = os.path.join(GLOBAL_SKILLS_DIR, "credential-manager", "cred_cli.py")
    if os.path.isfile(cred_cli_path):
        healthy.append("cred_cli.py exists")
    else:
        issues.append({
            "item": "cred_cli.py",
            "problem": f"Not found at {cred_cli_path}",
        })

    # Check 2: credential-registry.json is valid JSON
    if os.path.isfile(CREDENTIAL_REGISTRY):
        registry = _load_json(CREDENTIAL_REGISTRY)
        if registry is not None:
            cred_count = len(registry.get("credentials", []))
            healthy.append(f"credential-registry.json valid ({cred_count} credentials)")
        else:
            issues.append({
                "item": "credential-registry.json",
                "problem": "File exists but is not valid JSON",
            })
    else:
        issues.append({
            "item": "credential-registry.json",
            "problem": f"Not found at {CREDENTIAL_REGISTRY} (system may not be set up yet)",
        })

    # Check 3: Scan known .env files for plaintext tokens
    for service_name, env_path in KNOWN_ENV_FILES:
        if not os.path.isfile(env_path):
            # .env file doesn't exist -- not an issue
            continue

        plaintext_issues = _scan_env_for_plaintext(env_path, service_name)
        if plaintext_issues:
            issues.extend(plaintext_issues)
        else:
            healthy.append(f"{service_name}/.env (no plaintext secrets)")

    return {"healthy": healthy, "issues": issues}


if __name__ == "__main__":
    result = run()
    print(f"Healthy: {len(result['healthy'])}")
    for h in result["healthy"]:
        print(f"  [OK] {h}")
    if result["issues"]:
        print(f"\nIssues: {len(result['issues'])}")
        for issue in result["issues"]:
            print(f"  [!] {issue['item']}: {issue['problem']}")
    else:
        print("\nNo issues found.")
