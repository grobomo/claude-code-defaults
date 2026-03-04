---
id: gui-troubleshooting
name: GUI Troubleshooting (tkinter)
keywords: [gui, window, tkinter, popup, dialog, display, not appearing]
enabled: true
priority: 5
action: Check GUI relaunch and display context
---

# GUI Troubleshooting

## WHY
Python tkinter GUIs (like store_gui.py) can fail to render depending on how they're launched. Claude Code's Bash tool runs commands through Git Bash (Windows) or a shell subprocess (Mac/Linux) that may lack proper GUI session access. The window enters mainloop but never becomes visible.

## Known Issue: Tkinter Window Not Appearing

### Root Cause
Claude Code spawns a shell subprocess. On Windows, Git Bash/MSYS2 creates child processes in a console session that can't always render desktop GUI windows. On headless Linux, there's no DISPLAY server.

### How store_gui.py Handles It
The script auto-detects non-GUI contexts and relaunches itself as a detached process:
- **Windows**: `subprocess.Popen` with `CREATE_NEW_CONSOLE` flag
- **Linux/macOS**: `subprocess.Popen` with `start_new_session=True`
- **Detection**: checks `MSYSTEM`, `TERM_PROGRAM`, `CLAUDE_CODE` env vars (Windows) or `DISPLAY`/`WAYLAND_DISPLAY` (Unix)
- **Loop prevention**: `_STORE_GUI_RELAUNCHED` env flag

### If GUI Still Doesn't Appear

1. **Check if process is running**: `ps aux | grep store_gui` or Task Manager
2. **Try manual launch outside Claude Code**: open a native terminal (cmd.exe, Terminal.app, xterm) and run `python ~/.claude/super-manager/credentials/store_gui.py KEY_NAME`
3. **Check DISPLAY (Linux)**: `echo $DISPLAY` -- must be set (e.g., `:0`) for tkinter
4. **Check Python has tkinter**: `python -c "import tkinter; print('ok')"`

### Cross-Platform Notes
- Fonts: Segoe UI + Consolas on Windows, TkDefaultFont + monospace on Unix
- `-topmost` attribute: wrapped in try/except, not all platforms support it
- `secure_zero`: uses ctypes.memset with fallback to byte-level zeroing
- OS credential backends: Windows Credential Manager (DPAPI), macOS Keychain, Linux SecretService (requires `secretstorage` or `keyrings.alt`)
