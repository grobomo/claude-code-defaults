---
id: winremote-routing
name: WinRemote MCP Routing
keywords: [winremote, remote desktop, visual control, ec2 desktop]
enabled: true
priority: 10
action: Use winremote MCP for remote Windows desktop control
min_matches: 1
---

# WinRemote MCP Routing

## WHY

WinRemote is an HTTP MCP server running on EC2 Windows Server. It provides 44 tools for full desktop control (screenshots, clicks, typing, shell, files, registry, services). Using it correctly requires knowing the right tool names and the session architecture.

## Instance Details

| Key | Value |
|-----|-------|
| Instance | i-0bea75213c8d82bb7 (win-ztsa-test, t3.medium) |
| Public IP | 3.133.121.203 (changes on reboot -- check with `aws ec2 describe-instances`) |
| MCP endpoint | http://<IP>:8090/mcp |
| Auth | Bearer wr-lab-2026-secret |
| OS | Windows Server 2022, Administrator |
| Persistence | Auto-logon + shell:startup bat launches winremote-mcp in interactive session |

## How to Use

1. Start the MCP: `mcp__mcp-manager__mcpm(operation="start", server="winremote")`
2. Take screenshot: `mcp__mcp-manager__mcpm(operation="call", server="winremote", tool="Snapshot")`
3. Click: `mcp__mcp-manager__mcpm(operation="call", server="winremote", tool="Click", arguments={"x": 500, "y": 300})`
4. Type: `mcp__mcp-manager__mcpm(operation="call", server="winremote", tool="Type", arguments={"text": "hello"})`
5. Shell: `mcp__mcp-manager__mcpm(operation="call", server="winremote", tool="Shell", arguments={"command": "dir C:\\"})`

## Key Tool Names (case-sensitive)

| Tool | Purpose |
|------|---------|
| **Snapshot** | Screenshot + window list + UI elements (NOT "take_screenshot") |
| **AnnotatedSnapshot** | Screenshot with numbered labels on UI elements |
| **Click** | Mouse click at x,y coordinates |
| **Type** | Type text, optionally at coordinates |
| **Shell** | Execute PowerShell command |
| **App** | Launch/switch/resize applications |
| **FocusWindow** | Bring window to foreground by title |
| **OCR** | Extract text from screen region |
| **FileRead/FileWrite** | Read/write files on remote machine |
| **RegRead/RegWrite** | Windows registry operations |
| **ServiceList/ServiceStart/ServiceStop** | Windows services |

## Troubleshooting: Screenshot Fails ("screen grab failed")

This means winremote-mcp is running in **Session 0** (services session -- no desktop).

**Root cause:** Windows has Session 0 (services, no GUI) and Session 1+ (interactive desktop). winremote-mcp needs Session 1+.

**Fix:**
1. Check session: `Shell` -> `query user` (look for Active session)
2. Check process session: `Shell` -> `Get-Process winremote-mcp | Select-Object SessionId`
3. If SessionId is 0, kill it: `Shell` -> `Stop-Process -Name winremote-mcp -Force`
4. Relaunch in interactive session:
   ```
   Shell -> schtasks /create /tn "WinRemote" /tr "C:\Users\Administrator\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\winremote-mcp.bat" /sc once /st 00:00 /ru Administrator /rp "pRC&ob.2xh(4hBF.fYEUpFH%Q?=AQQu7" /it /f
   Shell -> schtasks /run /tn "WinRemote"
   Shell -> schtasks /delete /tn "WinRemote" /f
   ```
5. Wait 3 seconds, retry Snapshot

**Prevention:** The instance has auto-logon + startup bat configured. After reboot, winremote-mcp starts automatically in the user's interactive session.

## If Instance IP Changed (after reboot/stop-start)

1. Get new IP: `aws ec2 describe-instances --instance-ids i-0bea75213c8d82bb7 --query 'Reservations[0].Instances[0].PublicIpAddress' --output text --profile my-profile --region us-east-2`
2. Update servers.yaml winremote URL with new IP
3. Reload mcpm: `mcp__mcp-manager__mcpm(operation="reload")`
4. Restart winremote: `mcp__mcp-manager__mcpm(operation="stop", server="winremote")` then start

## Do NOT

- Do NOT use `take_screenshot` -- the tool is called `Snapshot`
- Do NOT run winremote-mcp as a Windows Service (session 0, no desktop)
- Do NOT use `start "" chrome` on the remote -- use `App` tool instead
- Do NOT assume the IP is static -- it changes on instance stop/start
