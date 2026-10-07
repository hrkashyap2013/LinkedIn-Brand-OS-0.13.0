---
description: Give 3 visual previews, then render the one the owner picks
argument-hint: [context, notes, or pasted material]
---

Use the visual-strategy subagent for the VISUAL BLUEPRINT, then the visual-learning subagent for 3 VISUAL PREVIEWS of different diagram types. Stop for decision 2 and ask the owner to pick one (or ask for ideas on a part). After the pick, use the visual-production subagent to render only that pick, then visual-qa.

Input from the user: $ARGUMENTS

Read the relevant files in `memory/` and `docs/` first. Return the agents' outputs as-is, then stop for the owner's decision.
