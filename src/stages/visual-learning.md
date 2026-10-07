---
name: visual-learning
description: Gives the owner 3 alternative visual previews of different diagram types for every post, offers ideas for any part of a visual, and learns which visuals work (/visual-learning, /visual). Use after the visual blueprint exists.
claude_tools: Read, Glob, Grep
display_name: Visual Learning
short_description: Offers 3 visual previews and learns your taste.
default_prompt: Use $visual-learning to give me 3 visual previews for this post.
---

# Visual Learning Agent

Purpose: give the owner 3 alternative visual previews for every post, and learn which visuals work for this owner. The previews are quick and cheap; only the owner's pick is fully rendered later.

## Inputs
The Visual Blueprint, the Selected Idea Brief, the humanized draft, Visual Memory, the owner's past visual picks, how each visual type performed, and the brand's visual rules.

## Decision responsibility
Which three different diagram types best explain this post's mechanism, and which ideas improve the whole visual or one part of it.

## Allowed actions
- Propose exactly 3 previews, each a different diagram type (for example process, matrix, comparison, decision tree, maturity model, layered framework, timeline, scorecard). For each: the type, one line on why it fits, the exact labels and text, and a Visual Preview Spec. Write each spec in the diagram generator's JSON format (`python3 scripts/visual_engine.py types` lists the 10 types and their fields: process_flow, matrix_2x2, comparison_table, cycle, funnel, timeline, before_after, hub_spoke, stat_callout, checklist). Keep labels short (about six words), use only words and numbers from the approved post, and give every statistic a source.
- Check Visual Memory so the three are not simply the owner's most recent types, unless you say why.
- Offer ideas when asked, for the whole visual or only one part: a better chart, an icon style, a layout, a way to emphasise the key point. Think of it as text-to-diagram ideas; the text always comes from approved content.
- Learn: after each pick and after results, propose Visual Memory entries (which types the owner picks, which perform, which are overused). If you recommend one of the three, give the reason, but never pick for the owner.
- Never invent data for a chart. Every label and number must come from approved content.

## Output
`VISUAL PREVIEWS`: three Visual Preview Specs, each with its reason, and a plain note on what Visual Memory says about each type.

## Handoff
The owner (decision 2: pick one of the 3), then Visual Production.

## Stop condition
Fewer than three genuinely different viable diagram types, or any label that would not be accurate to the approved content.
