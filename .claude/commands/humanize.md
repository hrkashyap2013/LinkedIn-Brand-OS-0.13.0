---
description: Humanize a draft
argument-hint: [context, notes, or pasted material]
---

Use the humanization subagent to refine this draft without changing its supported claims. When files are available, run `python3 scripts/ai_tells.py --file <draft>` before and `python3 scripts/ai_tells.py compare --before <draft> --after <edited>` after, and pass the reports on.

Input from the user: $ARGUMENTS

Read the relevant files in `memory/` and `docs/` first. Return the agents' outputs as-is, then stop for the owner's decision.
