---
description: Undo the last memory change
argument-hint: [context, notes, or pasted material]
---

Show the last entries with `python3 scripts/memory_guard.py history`, confirm with the owner, then run `python3 scripts/memory_guard.py undo`. Report what was restored.

Input from the user: $ARGUMENTS

Read the relevant files in `memory/` and `docs/` first. Return the agents' outputs as-is, then stop for the owner's decision.
