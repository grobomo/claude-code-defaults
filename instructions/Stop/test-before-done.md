---
id: test-before-done
name: Test Before Done
# Stop instructions use PATTERNS (regex) only, NEVER keywords.
pattern: (anything else|something else|moving on|done here|all set|wraps up|that covers|that should)
enabled: true
description: Remind Claude to test solutions before declaring done
---

# Test Before Wrapping Up

You're about to wrap up without verifying your changes work. Before saying "done":

- **Run the code** if you wrote/modified code (syntax check, import test, --help, etc.)
- **Verify the fix** if you fixed a bug (reproduce the scenario, check the output)
- **Check the config** if you changed config/settings (validate it loads, no typos)
- **Dry-run the command** if you set up a task/service (status check, test invocation)

If testing is truly not possible (e.g. requires user interaction like UAC, phone approval), state WHY you can't test and what the user should verify manually.
