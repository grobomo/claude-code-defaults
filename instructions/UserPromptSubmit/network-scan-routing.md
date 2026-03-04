---
id: network-scan-routing
name: network-scan Routing
keywords: [scan network, nmap, find devices, network devices]
enabled: true
priority: 10
action: Use network-scan skill
min_matches: 1
---

# network-scan Routing

## WHY
Scan local network for active devices using nmap via WSL. The network-scan skill is already configured
and authenticated. Using it is faster and more reliable than generic tools.

## Rule
When prompt asks to scan network, find devices, or discover hosts:

1. **Use network-scan skill** (preferred)
2. **Invoke via Skill tool**


## How
```
Skill tool: network-scan
```
