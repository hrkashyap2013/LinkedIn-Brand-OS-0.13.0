---
description: Prepare sending of the approved package (Posting)
argument-hint: [context, notes, or pasted material]
---

Use the posting subagent. First check that decisions 1 to 4 are in the Approval Log for this exact package; if not, say which is missing and stop. Ask the owner when they plan to post: at the schedule slot, now, or a custom date and time. Then follow the Orchestrator rules: run `python3 scripts/package_builder.py build --id <post-id>` to make the ready-to-paste folder (it refuses if any decision no longer matches), and hand it to the owner to post.

Input from the user: $ARGUMENTS

Read the relevant files in `memory/` and `docs/` first. Return the agents' outputs as-is, then stop for the owner's decision.
