---
description: Mark a post as live and choose reminder windows
argument-hint: [context, notes, or pasted material]
---

The owner says a post is live. Ask, one at a time: the post, the final text as posted, the link, and which reminder windows they want (24h, 72h, 7d, 15d, 30d, 60d, 90d). Save the final text in drafts/ next to the agent's draft so Humanization can learn from the edits. Record the Post Tracker entry through the write guard. Run `python3 scripts/postkit.py live --id <post-id> --url <link> --windows <chosen windows>`: it saves the tracker row and starts the reminders, which the scheduler fires as notifications (including ones that came due while the computer was off).

Input from the user: $ARGUMENTS

Read the relevant files in `memory/` and `docs/` first. Return the agents' outputs as-is, then stop for the owner's decision.
