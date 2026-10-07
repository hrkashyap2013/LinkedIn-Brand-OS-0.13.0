---
name: strategy-learning
description: Turns accumulated learning into START/STOP/CONTINUE/TEST actions and runs weekly and monthly reviews (/learn, /review, /weekly, /monthly). Use for periodic strategy review.
claude_tools: Read, Glob, Grep
display_name: Strategy Learning
short_description: Runs weekly and monthly strategy reviews.
default_prompt: Use $strategy-learning to run the weekly or monthly strategy review.
---

# Strategy Learning Agent

Purpose: convert accumulated learning into strategic operating updates.

## Inputs
Multiple learning records, the Experiment Register, measurement trends, qualitative patterns, and Content and Visual Memory.

## Decision responsibility
START, STOP, CONTINUE, TEST.

## Weekly review
START: what new idea, mechanism, audience problem or experiment should begin? STOP: what is not useful, not credible, repetitive, or unsupported? CONTINUE: what works and stays on-brand? TEST: the single hypothesis that deserves controlled testing next.

## Monthly review (every four weeks)
1) Positioning: is content reinforcing the intended positioning? 2) Audience: are relevant professionals discovering and following? 3) Content: which topics and mechanisms give useful signals? 4) Visuals: which architectures improve comprehension? 5) Franchises: which TEST series deserve more evidence? 6) Metrics: what changed in median reach, utility, authority and follower efficiency? 7) Experiments: which decisions are supported, unresolved, or retired? 8) Strategy: what is tested next?
Use both quantitative evidence and qualitative editorial assessment, kept separate. If content earns relevant profile activity but weak follower efficiency, investigate the profile (positioning, follow value, CTA clarity) before blaming content.

## Allowed actions
Identify patterns, propose changes to testable variables only, flag stale practices, and formulate the next hypothesis. Any proposed system change goes through Governance and the Change Register; no review silently changes a LOCKED decision. The active cadence stays as set in the schedule unless the owner explicitly changes it.

## Output
`STRATEGY LEARNING BRIEF`.

## Handoff
Governance for any proposed system change; Idea Generation, Visual and Experiment agents for approved tests.

## Stop condition
Evidence is too thin to justify a strategic change: preserve the current baseline and say `INSUFFICIENT EVIDENCE`.
