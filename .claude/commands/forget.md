---
description: Delete all stored data (asks you to confirm)
argument-hint: [context, notes, or pasted material]
---

Explain exactly what will be deleted (all register rows, runs, drafts, reports, inbox files and history; your docs stay). Ask the owner to type DELETE-MY-DATA to confirm. Only then run `python3 scripts/memory_guard.py forget --confirm DELETE-MY-DATA`.

Input from the user: $ARGUMENTS

Read the relevant files in `memory/` and `docs/` first. Return the agents' outputs as-is, then stop for the owner's decision.
