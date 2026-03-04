---
id: v1-console-navigation
name: V1 Console Navigation via Blueprint
keywords: [v1, console, navigate, page, blueprint, browser, click, menu]
description: "WHY: V1 is a SPA -- direct URL hash navigation and browser_navigate fail silently (redirect to dashboard). WHAT: Use sidebar clicks and JS evaluation instead."
enabled: true
priority: 10
action: Navigate V1 console via sidebar clicks, not URL hash
min_matches: 2
---

# V1 Console Navigation via Blueprint

## WHY

V1 console is a React SPA with Ant Design. Direct URL navigation (including hash fragments)
fails silently -- the app redirects to dashboard. `browser_navigate action='url'` with hash
paths like `#/app/endpoint-security-operations/...` does NOT work. The SPA router rejects
externally-set hashes.

## What Works

### 1. Vue Router Push (BEST -- always works)
V1 is a Vue app. Access the router and push directly:
```javascript
browser_evaluate:
  var vueApp = document.querySelector('#App').__vue_app__ || document.querySelector('#RootContainer').__vue_app__;
  var r = vueApp.config.globalProperties.$router;
  r.push('/app/epp/workload-protection');
```

### Key V1 Vue Routes
| Route | Page |
|-------|------|
| `/app/epp/workload-protection` | Server & Workload Protection (SWP) |
| `/app/epp/endpoint-protection` | Standard Endpoint Protection (SEP) |
| `/app/endpoint-inventory` | Endpoint Inventory |
| `/app/security-functions/endpoint-inventory` | Endpoint Inventory (alt) |
| `/app/policy/endpoint` | Endpoint Policy |
| `/app/zero/endpoints` | Zero Trust Endpoints |
| `/dashboard` | Dashboard |

To discover all routes:
```javascript
var r = vueApp.config.globalProperties.$router;
r.getRoutes().map(rt => rt.path).filter(p => p.includes('keyword'));
```

### 2. JS click on accessibility tree elements (backup)
Use `browser_snapshot` to get the tree, then `browser_evaluate` with
`document.querySelector('#menuID .ant-menu-submenu-title').click()`

### 3. Sidebar menu IDs (for JS click)
| Menu ID | Section |
|---------|---------|
| `#menuendpoint_security_operations` | Endpoint Security |
| `#menuxdr_app` | Agentic SIEM and XDR |
| `#menuserver_cloud_app` | Cloud Security |
| `#menuemail_security_operations` | Email Security |
| `#menunetwork_security_operations` | Network Security |
| `#menuzero_trust` | Zero Trust |
| `#menusetting` | Administration |

## What Does NOT Work

- `browser_navigate action='url' url='...#/app/...'` -- redirects to dashboard
- Setting `window.location.hash` alone -- SPA ignores passive hash changes
- Opening new tabs with V1 hash URLs -- always lands on dashboard
- Full URL reload with hash -- re-auth required, lands on dashboard

## V1 Sidebar Icon Order (top to bottom, left nav)

| Position | Icon | Section |
|----------|------|---------|
| 1 | Shield | Cyber Risk Overview |
| 2 | Eye | Exposure Management |
| 3 | Chart | Attack Surface |
| 4 | X | XDR |
| 5 | Grid | Workflow |
| 6 | Lock | Zero Trust |
| 7 | Box | Endpoint Security Operations |
| 8 | People | Identity Security |
| 9 | Document | Compliance |
| 10 | Cloud | Cloud Security |
| 11 | Envelope | Email Security |
| 12 | Shield+ | Network Security |
| 13 | Globe | Service Gateway |
| 14 | Gear | Administration |

## Tips

- Always take a screenshot AFTER navigation to verify you landed on the right page
- V1 pages take 3-5 seconds to fully load -- wait before interacting
- Dismiss popups (MFA, Companion, notices) before navigating -- they block clicks
- If sidebar is collapsed (icons only), click the `>>` at bottom to expand labels

## Do NOT

- Do NOT use browser_navigate with V1 hash URLs -- it will redirect to dashboard
- Do NOT assume URL-based navigation works in V1 SPA
- Do NOT keep retrying the same failed URL pattern
