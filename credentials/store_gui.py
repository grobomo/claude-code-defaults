#!/usr/bin/env python3
"""
store_gui.py - GUI popup for securely storing credentials.

Pops up a small dialog with a masked password field.
User pastes token, clicks Store, done. Zero friction.

Usage:
    python store_gui.py SERVICE/KEY          # Key name known
    python store_gui.py myservice/API_TOKEN
    python store_gui.py                      # Prompts for key name too
"""
import sys
import os
import gc
import ctypes
import tkinter as tk
from tkinter import messagebox

SERVICE = "claude-code"


def secure_zero(ba):
    """Zero out a bytearray's memory (best-effort)."""
    if ba and isinstance(ba, bytearray):
        # Zero via ctypes for reliability
        ctypes.memset((ctypes.c_char * len(ba)).from_buffer(ba), 0, len(ba))


def store_credential(key=None):
    """Pop up GUI to store a credential. If key is None, asks for both name and value."""
    root = tk.Tk()
    root.title("Store Credential")
    root.resizable(False, False)

    has_key = key is not None
    w = 420
    h = 160 if has_key else 200
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.attributes('-topmost', True)

    # Key name field (only if no key provided)
    key_entry = None
    if not has_key:
        tk.Label(root, text="Key name (e.g. myservice/API_TOKEN):", font=("Segoe UI", 10)).pack(pady=(10, 2))
        key_entry = tk.Entry(root, width=50, font=("Consolas", 10))
        key_entry.pack(pady=2, padx=20)
        key_entry.focus_set()

    # Value label
    label_text = f"Paste value for: {key}" if has_key else "Paste secret value:"
    tk.Label(root, text=label_text, font=("Segoe UI", 10)).pack(pady=(10 if has_key else 5, 2))

    # Password entry (masked)
    val_entry = tk.Entry(root, show="*", width=50, font=("Consolas", 10))
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
    tk.Button(btn_frame, text="Store", command=do_store, width=10, font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=5)
    tk.Button(btn_frame, text="Cancel", command=do_cancel, width=10, font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=5)

    root.bind('<Return>', do_store)
    root.bind('<Escape>', do_cancel)

    root.mainloop()

    # Final cleanup: force garbage collection
    del secret_buf
    gc.collect()

    return result["stored"], result["key"]


def main():
    key = sys.argv[1] if len(sys.argv) >= 2 else None

    # Check if already set (only if key provided)
    if key:
        try:
            import keyring
            existing = keyring.get_password(SERVICE, key)
            if existing:
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
