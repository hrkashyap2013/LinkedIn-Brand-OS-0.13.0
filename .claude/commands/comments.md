---
description: Triage comments on your post and draft replies (same as /reply)
argument-hint: [context, notes, or pasted material]
---

Use the reply subagent. The owner pastes the comments on their own post; if comments are in a file, first run `python3 scripts/reply_filter.py --file <file>` for a rule-based sort and pass it on. Flag risks and draft replies. The owner posts any reply; nothing is replied automatically.

Input from the user: $ARGUMENTS

Read the relevant files in `memory/` and `docs/` first. Return the agents' outputs as-is, then stop for the owner's decision.
