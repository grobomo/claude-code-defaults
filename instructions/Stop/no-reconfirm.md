---
id: no-reconfirm
name: No Re-confirmation
pattern: (ready to|go ahead|proceed with|shall we|confirm.{0,10}(before|first)).{0,50}\?
enabled: true
description: Never re-confirm actions the user already requested
# WHY: When the user gives a direct instruction ("disconnect and test"), Claude
# sometimes restates it as a question ("Ready to disconnect?") with y/n options.
# This wastes the user's time making them repeat themselves. The instruction was
# clear the first time -- just execute it.
---

# No Re-confirmation

The user already told you what to do. Do NOT restate their instruction as a question.

- User says "disconnect and test" -> disconnect and test. Do NOT ask "Ready to disconnect?"
- User says "push it" -> push. Do NOT ask "Push to origin/main?"
- User says "run it" -> run it. Do NOT ask "Go ahead and run?"
- User says "test first" -> test. Do NOT ask "Shall we proceed with testing?"

**WHY this matters:** Re-confirming wastes the user's time and makes them repeat themselves. If the user gave a clear action, execute it. The ONLY time to confirm is for genuinely destructive or ambiguous actions that the user did NOT explicitly request.
