---
description: Run visual QA, humanized QA and the quality gate
argument-hint: [context, notes, or pasted material]
---

Use the visual-qa subagent (with visual-strategy and governance as needed) to run visual QA, humanized QA, and the quality gate, and return a score out of 100.

Input from the user: $ARGUMENTS

Read the relevant files in `memory/` and `docs/` first. Return the agents' outputs as-is, then stop for the owner's decision.
