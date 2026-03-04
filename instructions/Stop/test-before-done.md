---
id: test-before-done
name: Test Before Wrapping Up
pattern: (moving on|done here|wraps up|that covers|changes look good|should (work|be good|be fine)|looks correct|here.s (the |a )?(full |final )?(results|summary|status)|all (done|set|complete|good|ready|processes)|everything (is |looks )(good|working|ready|set|fine)|works (perfectly|great|correctly|fine)|verified (working|complete)|savings verified|proof of concept|usage:|files (created|in |built))
description: "WHY: Claude claims work is done without measured verification. WHAT: Block any wrap-up response that declares completion without showing before/after evidence."
enabled: true
priority: 5
action: MEASURE before/after -- show numbers, not claims
---

You are about to declare your work done. STOP. Before wrapping up:

1. **Run the code** you wrote or modified
2. **Show measured output** -- actual numbers, not descriptions
3. **Compare before vs after** if you changed behavior
4. **If testing is impossible**, explain exactly why

"It works" is a guess. Measured output is evidence.
