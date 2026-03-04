"""
credential_manager.py - Manages API tokens and secrets using the OS credential store.

Stores credentials in the OS keyring (Windows Credential Manager, macOS Keychain)
via the Python `keyring` library.  The registry file tracks key *names* only ---
actual secret values NEVER appear in any file on disk.

Service namespace: "claude-code"
Key format: "<service>/<VARIABLE>"

Registry location: ~/.claude/super-manager/credentials/credential-registry.json
"""
import sys
import os
import re
import json
import platform
import subprocess
import getpass
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.configuration_paths import (
    CREDENTIALS_DIR,
    CREDENTIAL_REGISTRY,
    KNOWN_ENV_FILES,
    SECRET_PATTERNS,
)
from shared.logger import create_logger

log = create_logger("credential-manager")

try:
    import keyring
except ImportError:
    keyring = None
    log.error("keyring library not installed - credential operations will fail")

KEYRING_SERVICE = "claude-code"
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_registry():
    """Read credential-registry.json. Returns list of credential dicts."""
    os.makedirs(CREDENTIALS_DIR, exist_ok=True)
    try:
        with open(CREDENTIAL_REGISTRY, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    return data.get("credentials", [])


def _write_registry(credentials_list):
    """Write the registry file atomically. Stores key names only, never values."""
    os.makedirs(CREDENTIALS_DIR, exist_ok=True)
    data = {
        "credentials": [
            {
                "key": c["key"],
                "service": c["service"],
                "variable": c["variable"],
                "added": c.get("added", datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")),
            }
            for c in credentials_list
        ],
    }
    tmp_path = CREDENTIAL_REGISTRY + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp_path, CREDENTIAL_REGISTRY)


def _find_registry_entry(key, credentials_list):
    """Find a credential in the registry by its full key (service/VARIABLE)."""
    for c in credentials_list:
        if c.get("key") == key:
            return c
    return None


def _parse_key(key):
    """Parse 'service/VARIABLE' into (service, variable). Returns None on bad format."""
    if "/" not in key:
        return None
    parts = key.split("/", 1)
    if not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def _is_secret_variable(var_name):
    """Returns True if var_name contains any of SECRET_PATTERNS (case-insensitive)."""
    upper = var_name.upper()
    return any(pat in upper for pat in SECRET_PATTERNS)


def _is_credential_ref(value):
    """Returns True if value starts with 'credential:'."""
    return value.strip().startswith("credential:")


def _read_clipboard():
    """Read the current clipboard contents using platform-specific commands."""
    try:
        if IS_WINDOWS:
            return subprocess.check_output(
                ["powershell", "-c", "Get-Clipboard"], text=True
            ).strip()
        elif IS_MAC:
            return subprocess.check_output(["pbpaste"], text=True).strip()
        else:
            # Linux - try xclip, then xsel
            try:
                return subprocess.check_output(
                    ["xclip", "-selection", "clipboard", "-o"], text=True
                ).strip()
            except FileNotFoundError:
                return subprocess.check_output(
                    ["xsel", "--clipboard", "--output"], text=True
                ).strip()
    except subprocess.CalledProcessError as exc:
        log.error("_read_clipboard: command failed: {}".format(exc))
        return None


def _ensure_keyring():
    """Check that keyring is available. Returns error message or None."""
    if keyring is None:
        return "keyring library not installed. Run: pip install keyring"
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_all(service_filter=None):
    """
    List all registered credentials with their stored status.
    NEVER includes credential values in output.

    Args:
        service_filter: If provided, only show credentials for this service.

    Returns:
        {"items": [...], "summary": "N credentials across M services"}
        Each item: {key, service, variable, stored (bool), added}
    """
    log.debug("list_all: reading credential registry (filter={})".format(service_filter))
    err = _ensure_keyring()
    if err:
        log.error("list_all: {}".format(err))
        return {"items": [], "summary": err}

    credentials = _read_registry()
    items = []

    for cred in credentials:
        key = cred.get("key", "")
        service = cred.get("service", "")
        # Derive variable from key if missing (older entries may lack it)
        variable = cred.get("variable") or (key.split("/", 1)[1] if "/" in key else key)
        added = cred.get("added", "")

        if service_filter and service != service_filter:
            continue

        # Check if the value can actually be resolved from the keyring
        try:
            val = keyring.get_password(KEYRING_SERVICE, key)
            stored = val is not None
        except Exception:
            stored = False

        items.append({
            "key": key,
            "service": service,
            "variable": variable,
            "stored": stored,
            "added": added,
        })

    services = set(i["service"] for i in items)
    summary = "{} credentials across {} services".format(len(items), len(services))
    log.info("list_all: {}".format(summary))
    return {"items": items, "summary": summary}


def store_credential(key, value=None, clipboard=False, stdin=False):
    """
    Store a credential in the OS credential store.

    Args:
        key:       "service/VARIABLE" format (e.g. "wiki-lite/CONFLUENCE_API_TOKEN")
        value:     The secret value (if provided directly).
        clipboard: If True, read value from clipboard.
        stdin:     If True, read value from stdin.

    Returns:
        {"success": bool, "message": str}
    """
    log.info("store_credential: key={}".format(key))
    err = _ensure_keyring()
    if err:
        return {"success": False, "message": err}

    parsed = _parse_key(key)
    if not parsed:
        msg = "Invalid key format. Expected 'service/VARIABLE', got: {}".format(repr(key))
        log.error("store_credential: {}".format(msg))
        return {"success": False, "message": msg}

    service, variable = parsed

    # Resolve the secret value from the appropriate source
    if clipboard:
        value = _read_clipboard()
        if value is None:
            msg = "Failed to read clipboard"
            log.error("store_credential: {}".format(msg))
            return {"success": False, "message": msg}
        if not value:
            msg = "Clipboard is empty"
            log.error("store_credential: {}".format(msg))
            return {"success": False, "message": msg}
    elif stdin:
        try:
            value = sys.stdin.read().strip()
        except Exception as exc:
            msg = "Failed to read stdin: {}".format(exc)
            log.error("store_credential: {}".format(msg))
            return {"success": False, "message": msg}
    elif value is None:
        try:
            value = getpass.getpass("Enter value for {}: ".format(key))
        except Exception as exc:
            msg = "Failed to read password input: {}".format(exc)
            log.error("store_credential: {}".format(msg))
            return {"success": False, "message": msg}

    if not value:
        msg = "Cannot store empty value for {}".format(key)
        log.error("store_credential: {}".format(msg))
        return {"success": False, "message": msg}

    # Store in OS keyring
    try:
        keyring.set_password(KEYRING_SERVICE, key, value)
    except Exception as exc:
        msg = "Keyring storage failed for {}: {}".format(key, exc)
        log.error("store_credential: {}".format(msg))
        return {"success": False, "message": msg}

    # Update registry (add or update entry)
    credentials = _read_registry()
    existing = _find_registry_entry(key, credentials)
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    if existing:
        existing["added"] = now  # update timestamp
    else:
        credentials.append({
            "key": key,
            "service": service,
            "variable": variable,
            "added": now,
        })
    _write_registry(credentials)

    msg = "Stored: {}".format(key)
    log.info("store_credential: {}".format(msg))
    return {"success": True, "message": msg}


def remove_item(key):
    """
    Delete a credential from OS store and registry.
    Archives the registry entry before removing.

    Returns:
        {"success": bool, "message": str}
    """
    log.info("remove_item: removing {}".format(key))
    err = _ensure_keyring()
    if err:
        return {"success": False, "message": err}

    credentials = _read_registry()
    existing = _find_registry_entry(key, credentials)

    if not existing:
        msg = "Credential {} not found in registry".format(repr(key))
        log.error("remove_item: {}".format(msg))
        return {"success": False, "message": msg}

    # Archive the registry entry to a dated file before removing
    archive_path = os.path.join(
        CREDENTIALS_DIR,
        "archived-credentials.jsonl",
    )
    os.makedirs(CREDENTIALS_DIR, exist_ok=True)
    archive_entry = dict(existing)
    archive_entry["archived_at"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(archive_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(archive_entry, ensure_ascii=False) + "\n")
    log.info("remove_item: archived registry entry for {} -> {}".format(key, archive_path))

    # Delete from OS keyring
    try:
        keyring.delete_password(KEYRING_SERVICE, key)
        log.info("remove_item: deleted {} from OS keyring".format(key))
    except keyring.errors.PasswordDeleteError:
        log.warn("remove_item: {} not found in OS keyring (already deleted?)".format(key))
    except Exception as exc:
        log.warn("remove_item: keyring delete failed for {}: {}".format(key, exc))

    # Remove from registry
    credentials = [c for c in credentials if c.get("key") != key]
    _write_registry(credentials)

    msg = "Removed credential {} (entry archived)".format(repr(key))
    log.info("remove_item: {}".format(msg))
    return {"success": True, "message": msg}


def get_value(key):
    """
    Resolve a single credential from the OS store.
    Returns the secret value string, or None if not found.

    Used by helper libraries, NOT by Claude (values must not appear in chat).
    """
    err = _ensure_keyring()
    if err:
        log.error("get_value: {}".format(err))
        return None

    try:
        value = keyring.get_password(KEYRING_SERVICE, key)
        if value is None:
            log.warn("get_value: {} not found in OS keyring".format(key))
        return value
    except Exception as exc:
        log.error("get_value: failed to read {}: {}".format(key, exc))
        return None


def migrate_env(env_path, service):
    """
    Migrate plaintext secrets from a .env file into the OS credential store.

    1. Read the .env file
    2. For each KEY=VALUE where the variable name matches SECRET_PATTERNS
       and the value is not already a credential: reference, store in keyring
    3. Rewrite the .env file replacing plaintext secrets with credential:service/VARIABLE
    4. Return summary of what was migrated

    Args:
        env_path: Absolute path to the .env file.
        service:  Service name (e.g. "wiki-lite").

    Returns:
        {"success": bool, "message": str, "migrated": [...], "skipped": [...]}
    """
    log.info("migrate_env: {} (service={})".format(env_path, service))
    err = _ensure_keyring()
    if err:
        return {"success": False, "message": err, "migrated": [], "skipped": []}

    if not os.path.isfile(env_path):
        msg = ".env file not found: {}".format(env_path)
        log.error("migrate_env: {}".format(msg))
        return {"success": False, "message": msg, "migrated": [], "skipped": []}

    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    migrated = []
    skipped = []
    new_lines = []
    credentials = _read_registry()
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    for line in lines:
        stripped = line.strip()

        # Preserve comments and blank lines
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        # Parse KEY=VALUE
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", stripped)
        if not match:
            new_lines.append(line)
            continue

        var_name = match.group(1)
        var_value = match.group(2).strip()

        # Remove surrounding quotes if present
        if len(var_value) >= 2 and var_value[0] in ('"', "'") and var_value[-1] == var_value[0]:
            var_value = var_value[1:-1]

        # Skip if not a secret variable
        if not _is_secret_variable(var_name):
            new_lines.append(line)
            skipped.append(var_name)
            continue

        # Skip if already a credential reference
        if _is_credential_ref(var_value):
            new_lines.append(line)
            skipped.append("{} (already credential ref)".format(var_name))
            continue

        # Skip empty values
        if not var_value:
            new_lines.append(line)
            skipped.append("{} (empty)".format(var_name))
            continue

        # Store in keyring
        key = "{}/{}".format(service, var_name)
        try:
            keyring.set_password(KEYRING_SERVICE, key, var_value)
        except Exception as exc:
            log.error("migrate_env: failed to store {}: {}".format(key, exc))
            new_lines.append(line)
            skipped.append("{} (keyring error)".format(var_name))
            continue

        # Update registry
        existing = _find_registry_entry(key, credentials)
        if existing:
            existing["added"] = now
        else:
            credentials.append({
                "key": key,
                "service": service,
                "variable": var_name,
                "added": now,
            })

        # Rewrite line with credential reference
        new_lines.append("{}=credential:{}\n".format(var_name, key))
        migrated.append(key)
        log.info("migrate_env: migrated {} -> credential:{}".format(var_name, key))

    # Write updated .env file
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    # Write updated registry
    _write_registry(credentials)

    msg = "Migrated {} secrets from {} ({} skipped)".format(
        len(migrated), os.path.basename(env_path), len(skipped)
    )
    log.info("migrate_env: {}".format(msg))
    return {"success": True, "message": msg, "migrated": migrated, "skipped": skipped}


def verify_all():
    """
    Health check for all credentials.

    1. For each credential in registry, verify it can be resolved from keyring.
    2. Cross-reference with KNOWN_ENV_FILES to check for plaintext leaks.

    Returns:
        {"healthy": [...], "issues": [...]}
        Each issue: {"item": str, "problem": str, "fix": str}
    """
    log.info("verify_all: running credential health check")
    err = _ensure_keyring()
    if err:
        return {"healthy": [], "issues": [{"item": "keyring", "problem": err, "fix": "pip install keyring"}]}

    credentials = _read_registry()
    healthy = []
    issues = []

    # 1. Check each registered credential can be resolved
    for cred in credentials:
        key = cred["key"]
        try:
            val = keyring.get_password(KEYRING_SERVICE, key)
            if val is not None:
                healthy.append(key)
            else:
                issues.append({
                    "item": key,
                    "problem": "Registered but not found in OS keyring",
                    "fix": "Run store_credential({}) to re-store the value".format(repr(key)),
                })
        except Exception as exc:
            issues.append({
                "item": key,
                "problem": "Keyring read error: {}".format(exc),
                "fix": "Check keyring backend configuration",
            })

    # 2. Cross-reference with KNOWN_ENV_FILES for plaintext secrets
    for service, env_path in KNOWN_ENV_FILES:
        if not os.path.isfile(env_path):
            continue
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", stripped)
                    if not match:
                        continue
                    var_name = match.group(1)
                    var_value = match.group(2).strip()
                    if _is_secret_variable(var_name) and var_value and not _is_credential_ref(var_value):
                        issues.append({
                            "item": "{}/{}".format(service, var_name),
                            "problem": "Plaintext secret in {}".format(env_path),
                            "fix": "Run migrate_env({}, {})".format(repr(env_path), repr(service)),
                        })
        except Exception as exc:
            log.warn("verify_all: could not read {}: {}".format(env_path, exc))

    log.info("verify_all: {} healthy, {} issues".format(len(healthy), len(issues)))
    return {"healthy": healthy, "issues": issues}


def audit_plaintext():
    """
    Scan KNOWN_ENV_FILES for plaintext tokens that should be migrated.

    For each .env file, reads lines and checks if variable names contain
    SECRET_PATTERNS. Values that are NOT credential: prefixed are flagged.

    Returns:
        {"findings": [...], "summary": str}
        Each finding: {"file": str, "service": str, "variable": str, "migrate_command": str}
    """
    log.info("audit_plaintext: scanning known .env files")
    findings = []

    for service, env_path in KNOWN_ENV_FILES:
        if not os.path.isfile(env_path):
            continue
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", stripped)
                    if not match:
                        continue
                    var_name = match.group(1)
                    var_value = match.group(2).strip()
                    if _is_secret_variable(var_name) and var_value and not _is_credential_ref(var_value):
                        findings.append({
                            "file": env_path,
                            "service": service,
                            "variable": var_name,
                            "migrate_command": "migrate_env({}, {})".format(repr(env_path), repr(service)),
                        })
        except Exception as exc:
            log.warn("audit_plaintext: could not read {}: {}".format(env_path, exc))

    files_scanned = sum(1 for _, p in KNOWN_ENV_FILES if os.path.isfile(p))
    summary = "{} plaintext secrets found across {} .env files scanned".format(
        len(findings), files_scanned
    )
    log.info("audit_plaintext: {}".format(summary))
    return {"findings": findings, "summary": summary}
