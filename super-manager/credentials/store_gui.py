#!/usr/bin/env python3
"""
store_gui.py - GUI popup for securely storing credentials.

Pops up a small dialog with a masked password field.
User pastes token, clicks Store, done. Zero friction.

Usage:
    python store_gui.py SERVICE/KEY          # Key name known
    python store_gui.py grobomo/GITHUB_TOKEN
    python store_gui.py                      # Prompts for key name too
"""
import sys
import os
import gc
import ctypes
import subprocess

SERVICE = "claude-code"
SCRIPT_PATH = os.path.normpath(os.path.abspath(__file__))


def _needs_relaunch():
    """Detect if we're in a non-GUI-capable shell context.

    WHY: When Claude Code's Bash tool runs Python, the subprocess inherits a
    console environment that can't always render tkinter windows. On Windows
    with Git Bash/MSYS2, the window enters mainloop but never appears. On
    headless Linux (no DISPLAY), tkinter crashes. Relaunching as a detached
    process with proper session access fixes both cases.
    """
    # Already relaunched - env flag prevents infinite loop
    if os.environ.get('_STORE_GUI_RELAUNCHED'):
        return False

    if os.name == 'nt':
        # MSYSTEM = Git Bash / MSYS2, CLAUDE_CODE = Claude Code shell
        if os.environ.get('MSYSTEM'):
            return True
        if os.environ.get('TERM_PROGRAM') == 'mintty':
            return True
        if os.environ.get('CLAUDE_CODE'):
            return True
    else:
        # Unix: headless (no display server) can't render tkinter
        if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
            return True

    return False


def _relaunch():
    """Relaunch this script as a detached process with GUI access.

    Cross-platform: uses CREATE_NEW_CONSOLE on Windows, start_new_session on Unix.
    Child stdout is captured via temp file since the new process is detached.
    Returns the child exit code, or None if relaunch fails.
    """
    import tempfile
    out_file = os.path.join(tempfile.gettempdir(), '_store_gui_out.txt')
    env = {**os.environ, '_STORE_GUI_RELAUNCHED': '1'}
    args = [sys.executable, SCRIPT_PATH] + sys.argv[1:]

    try:
        with open(out_file, 'w') as f:
            kwargs = dict(stdout=f, stderr=subprocess.STDOUT, env=env)
            if os.name == 'nt':
                # CREATE_NEW_CONSOLE gives child its own desktop-connected session
                kwargs['creationflags'] = subprocess.CREATE_NEW_CONSOLE
            else:
                # start_new_session detaches from parent's terminal session
                kwargs['start_new_session'] = True
            proc = subprocess.Popen(args, **kwargs)

        proc.wait()

        # Read and forward child stdout
        if os.path.exists(out_file):
            with open(out_file) as f:
                child_out = f.read().strip()
            try:
                os.unlink(out_file)
            except OSError:
                pass
            if child_out:
                print(child_out)
        return proc.returncode
    except Exception as e:
        print(f"GUI relaunch failed: {e}", file=sys.stderr)
        return None


def _import_tk():
    """Lazy-import tkinter (not needed if we relaunch)."""
    import tkinter as tk
    from tkinter import messagebox
    return tk, messagebox


def secure_zero(ba):
    """Zero out a bytearray's memory (best-effort, cross-platform)."""
    if ba and isinstance(ba, bytearray):
        try:
            ctypes.memset((ctypes.c_char * len(ba)).from_buffer(ba), 0, len(ba))
        except Exception:
            # Fallback: overwrite bytes directly (less reliable but works everywhere)
            for i in range(len(ba)):
                ba[i] = 0


def store_credential(key=None):
    """Pop up GUI to store a credential. If key is None, asks for both name and value."""
    tk, messagebox = _import_tk()
    root = tk.Tk()
    root.title("Store Credential")
    root.resizable(False, False)

    # Cross-platform fonts: Segoe UI is Windows, use TkDefaultFont as fallback
    ui_font = ("Segoe UI", 10) if os.name == 'nt' else ("TkDefaultFont", 10)
    mono_font = ("Consolas", 10) if os.name == 'nt' else ("monospace", 10)

    has_key = key is not None
    w = 420
    h = 160 if has_key else 200
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")
    try:
        root.attributes('-topmost', True)
    except tk.TclError:
        pass  # Not all platforms support -topmost

    # Key name field (only if no key provided)
    key_entry = None
    if not has_key:
        tk.Label(root, text="Key name (e.g. grobomo/GITHUB_TOKEN):", font=ui_font).pack(pady=(10, 2))
        key_entry = tk.Entry(root, width=50, font=mono_font)
        key_entry.pack(pady=2, padx=20)
        key_entry.focus_set()

    # Value label
    label_text = f"Paste value for: {key}" if has_key else "Paste secret value:"
    tk.Label(root, text=label_text, font=ui_font).pack(pady=(10 if has_key else 5, 2))

    # Password entry (masked)
    val_entry = tk.Entry(root, show="*", width=50, font=mono_font)
    val_entry.pack(pady=2, padx=20)
    if has_key:
        val_entry.focus_set()

    result = {"stored": False, "key": key}
    secret_buf = None

    def do_store(event=None):
        nonlocal secret_buf

        # Get key name
        final_key = key if has_key else (key_entry.get().strip() if key_entry else "")
        if not final_key:
            messagebox.showwarning("Missing", "Enter a key name.")
            return

        # Get value into bytearray for secure zeroing later
        raw_value = val_entry.get().strip()
        if not raw_value:
            messagebox.showwarning("Empty", "No value entered.")
            return
        secret_buf = bytearray(raw_value.encode('utf-8'))

        try:
            import keyring
            keyring.set_password(SERVICE, final_key, secret_buf.decode('utf-8'))
            result["stored"] = True
            result["key"] = final_key
        except Exception as e:
            messagebox.showerror("Error", f"Failed to store: {e}")
            return
        finally:
            # Secure cleanup: zero the buffer, clear the entry widget
            if secret_buf:
                secure_zero(secret_buf)
            val_entry.delete(0, tk.END)

        root.destroy()

    def do_cancel(event=None):
        # Clear entry before closing
        val_entry.delete(0, tk.END)
        root.destroy()

    # Buttons
    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=8)
    tk.Button(btn_frame, text="Store", command=do_store, width=10, font=ui_font).pack(side=tk.LEFT, padx=5)
    tk.Button(btn_frame, text="Cancel", command=do_cancel, width=10, font=ui_font).pack(side=tk.LEFT, padx=5)

    root.bind('<Return>', do_store)
    root.bind('<Escape>', do_cancel)

    root.mainloop()

    # Final cleanup: force garbage collection
    del secret_buf
    gc.collect()

    return result["stored"], result["key"]


def main():
    # WHY: Git Bash / MSYS2 / Claude Code subprocess can't render tkinter windows.
    # Relaunch as detached process with proper GUI session access.
    if _needs_relaunch():
        rc = _relaunch()
        sys.exit(rc if rc is not None else 1)

    key = sys.argv[1] if len(sys.argv) >= 2 else None

    # Check if already set (only if key provided)
    if key:
        try:
            import keyring
            existing = keyring.get_password(SERVICE, key)
            if existing:
                tk, messagebox = _import_tk()
                root = tk.Tk()
                root.withdraw()
                overwrite = messagebox.askyesno(
                    "Overwrite?",
                    f"{key} already has a stored value.\nOverwrite it?"
                )
                root.destroy()
                if not overwrite:
                    print("Cancelled.")
                    sys.exit(0)
        except Exception:
            pass

    stored, final_key = store_credential(key)

    if stored and final_key:
        # Update registry
        try:
            registry_path = os.path.join(os.path.dirname(__file__), "credential-registry.json")
            if os.path.exists(registry_path):
                import json
                with open(registry_path) as f:
                    data = json.load(f)
                creds = data.get("credentials", [])
                if not any(c.get("key") == final_key for c in creds):
                    creds.append({"key": final_key, "service": SERVICE})
                    data["credentials"] = creds
                    with open(registry_path, "w") as f:
                        json.dump(data, f, indent=2)
        except Exception:
            pass

        print(f"OK - {final_key} stored in credential manager")
    else:
        print("Cancelled.")
        sys.exit(1)


if __name__ == "__main__":
    main()
