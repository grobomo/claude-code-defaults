---
id: no-reconfirm
name: No Re-confirmation
pattern: ((?<!["`])want me to .+\?|(?<!["`])shall (we|i) .+\?|(?<!["`])ready to (disconnect|push|deploy|run|test).+\?|(?<!["`])go ahead and .+\?|(?<!["`])should i proceed\?|(?<!["`])do you want me .+\?)
description: Never re-confirm actions the user already requested
enabled: true
priority: 100
action: Execute user requests immediately without re-confirming
# WHY: When the user gives a direct instruction ("disconnect and test"), Claude
# sometimes restates it as a question ("Ready to disconnect?") with y/n options.
# This wastes the user's time making them repeat themselves. The instruction was
# clear the first time -- just execute it.
---

Do NOT restate the user's instruction as a question. Execute it directly. Only confirm genuinely destructive actions the user did NOT explicitly request.
