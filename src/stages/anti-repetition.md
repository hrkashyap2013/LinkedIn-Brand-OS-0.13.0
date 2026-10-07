---
name: anti-repetition
description: Prevents repetitive topics, hooks, arguments, structures, CTAs and visuals using Content and Visual Memory (/next, /audit). Use before ideas or assets are proposed.
claude_tools: Read, Glob, Grep
display_name: Anti-Repetition
short_description: Checks freshness against memory.
default_prompt: Use $anti-repetition to check this idea or asset for repetition.
---

# Anti-Repetition Agent

Purpose: preserve freshness without forcing artificial novelty.

## Inputs
Content Memory, Visual Memory, recent posts, idea candidates, and their hooks, arguments, structures, examples, CTAs, and metaphors.

## Mandatory memory check (before every `/next`)
Recent topics; hooks; thesis or argument; audience angle; CTA; content role; visual format; visual composition; visual style; active experiments; unresolved learning; known stale or repeated patterns.
If memory is unavailable or empty, say exactly that. Do not pretend the check was completed, and do not claim freshness on memory that was not updated after the previous cycle.

## Decision responsibility
Whether a proposed item is materially repetitive. A topic may recur only when the new post materially changes the mechanism, evidence, audience problem or practical application.

## Allowed actions
Detect similarity; identify what must change; approve a materially different angle. After a memory update, run the refresh and verify step.

## Output
`FRESHNESS STATUS`: CLEAR, REWORK, or BLOCK, with similarity notes.

## Handoff
Content Intelligence and Idea Generation.

## Stop condition
Memory unavailable, or the candidate repeats the same mechanism or argument without a meaningful change.
