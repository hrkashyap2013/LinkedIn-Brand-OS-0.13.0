---
description: Interview me and store my real stories (only when you ask)
argument-hint: [context, notes, or pasted material]
---

Use the interviewer subagent to interview the owner, one question at a time. Keep asking until the owner stops. When it returns an INTERVIEW SUMMARY, have the listening subagent check each REGISTER ENTRY, then apply them with `python3 scripts/memory_guard.py apply --agent interviewer --file <entries file>`. Confirm what was stored.

Input from the user: $ARGUMENTS

Read the relevant files in `memory/` and `docs/` first. Return the agents' outputs as-is, then stop for the owner's decision.
