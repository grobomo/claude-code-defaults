---
id: v1-console-always-signed-in
name: V1 Lab Console Always Signed In
keywords: [v1, console, sign, login, signed, incognito]
description: "WHY: V1 lab console is kept signed in on local incognito Chrome. Assuming sign-in is needed wastes time. WHAT: Take a screenshot to verify before assuming login is required."
enabled: true
priority: 10
action: V1 lab console is signed in locally -- screenshot to verify
min_matches: 2
---

# V1 Lab Console Always Signed In

## WHY

The V1 lab console is always kept signed in via a LOCAL incognito Chrome window on the
user's machine. Previous sessions wasted time trying to automate login or asking for
credentials when the console was already accessible.

## Rule

1. **V1 lab is ALWAYS in a local incognito Chrome window** -- use Blueprint to interact
2. **Assume it's signed in** -- the user keeps a persistent incognito session
3. **If unsure, take a screenshot** via Blueprint to verify
4. **Never ask for V1 console credentials** -- the session is already there
5. **Use winremote for the EC2 endpoint** -- not for V1 console

## Do NOT

- Do NOT assume V1 console needs login without taking a screenshot first
- Do NOT ask user for V1 console credentials
- Do NOT launch credential store GUI for V1 console login
- Do NOT try to open V1 console on the EC2 via winremote -- it's on the local machine
- Do NOT open V1 in regular (non-incognito) Chrome window
