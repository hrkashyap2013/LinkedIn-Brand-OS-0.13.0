---
description: Record measurement and experiment status
argument-hint: [context, notes, or pasted material]
---

If the owner supplied a CSV analytics export, first run `python3 scripts/metrics.py <file>` and pass its output on. Otherwise offer guided entry, a pasted table or a screenshot. Then use the measurement subagent for the MEASUREMENT RECORD and the experiment subagent for the EXPERIMENT STATUS.

Input from the user: $ARGUMENTS

Read the relevant files in `memory/` and `docs/` first. Return the agents' outputs as-is, then stop for the owner's decision.
