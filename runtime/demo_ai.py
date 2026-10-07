#!/usr/bin/env python3
"""A stand-in "AI" for demo mode and the tests. It reads a request on standard input and prints a canned answer.

It needs no account, key or network, and costs nothing. It is NOT an AI: it ignores what the request says
except for the stage marker and a few quoted values, so the demo is a click-through of the real app, engine,
approvals and package builder with fixed sample text about a fictional coaching business.

    echo "LBA-STAGE: ideas" | python3 scripts/demo_ai.py

Environment switches used by the tests and the guided demo:
    LBA_DEMO_EVIDENCE_GAP=1   the first draft stops with INSUFFICIENT EVIDENCE until real support is supplied
    LBA_DEMO_FAIL=<stage>     that stage returns unusable text (to test error handling)
    LBA_DEMO_BAD_JSON_ONCE=1  the first answer of each stage is malformed JSON, then correct (tests the automatic retry)
"""
import json
import os
import re
import sys

BRAND = "Brightpath Coaching"          # a fictional sample brand


def fenced(obj):
    return "Here is the result.\n\n```json\n%s\n```\n" % json.dumps(obj, indent=2)


def stage_of(prompt):
    m = re.search(r"^LBA-STAGE:\s*([a-z]+)", prompt, re.M)
    return m.group(1) if m else "chat"


def between(prompt, start, end=None):
    i = prompt.find(start)
    if i < 0:
        return ""
    i += len(start)
    j = prompt.find(end, i) if end else -1
    return prompt[i:j if j >= 0 else len(prompt)].strip()


def ideas(prompt):
    note = " (adjusted for your feedback)" if "Owner feedback to apply" in prompt else ""
    return {"governance": "PROCEED", "freshness_note": "Sample data: memory is empty, so nothing here is checked for repetition." + note,
            "ideas": [
                {"title": "Weekly reviews fail in week three", "angle": "A review needs one job, or it quietly dies.", "why_it_fits": "Practical advice for team leads.",
                 "proof_needed": "Your own experience running reviews."},
                {"title": "The five-minute handover", "angle": "Most dropped balls happen between people, not inside tasks.", "why_it_fits": "Shows a simple habit.",
                 "proof_needed": "One real example you can share without names."},
                {"title": "Stop calling it a quick sync", "angle": "Meetings with no owner produce no decisions.", "why_it_fits": "Conversation starter for managers.",
                 "proof_needed": "None beyond your experience."}],
            "notes": "This is sample content from the demo stand-in."}


def draft(prompt):
    gap = os.environ.get("LBA_DEMO_EVIDENCE_GAP") == "1" and "REAL SUPPORT SUPPLIED" not in prompt
    idea = between(prompt, "Chosen idea:", "\n") or "Weekly reviews fail in week three"
    if gap:
        return {"evidence_status": "INSUFFICIENT EVIDENCE", "evidence_gaps": ["A real example from your own team of a review that stopped working, and what you changed."],
                "post_text": "", "brief": {"claim": idea}}
    support = between(prompt, "REAL SUPPORT SUPPLIED BY THE OWNER (use only this as evidence; do not add facts):", "\n\n") if "REAL SUPPORT SUPPLIED" in prompt else ""
    extra = "\n\n(From your example: %s)" % support.splitlines()[0][:120] if support else ""
    tweak = "\n\nI changed this after your feedback." if "Owner feedback to apply" in prompt else ""
    return {"brief": {"claim": idea, "audience": "Team leads", "takeaway": "Give each review one job."}, "evidence_status": "OK", "evidence_gaps": [],
            "post_text": ("Most weekly reviews fail in week 3.\n\nNot because people are lazy.\nBecause nobody decided what the review is for.\n\n"
                          "Here is the four-step version I use:\n1. Name the outcome\n2. List the blockers\n3. Pick one lever\n4. Schedule step one\n\n"
                          "What is the one decision your review should always end with?" + extra + tweak),
            "first_comment": "If you want the one-page template, say so below and I will share it.", "pin_comment": "Template: name the outcome, list blockers, pick one lever, schedule step one.",
            "hashtags": ["leadership", "productivity", "teamwork"], "reply_starters": ["Good point. In week 3 the review usually loses its purpose."],
            "cta_type": "Conversation", "humanization_notes": "Shortened sentences; removed filler."}


def visuals(prompt):
    steps = {"type": "process_flow", "title": "A weekly review in four steps",
             "steps": [{"label": "Name the outcome"}, {"label": "List the blockers"}, {"label": "Pick one lever"}, {"label": "Schedule step one"}], "emphasis": 2,
             "takeaway": "One job per review."}
    matrix = {"type": "matrix_2x2", "title": "Where a review earns its time", "x_axis": {"label": "Effort", "low": "Low", "high": "High"},
              "y_axis": {"label": "Impact", "low": "Low", "high": "High"},
              "quadrants": [{"label": "Do now"}, {"label": "Plan it"}, {"label": "Skip it"}, {"label": "Drop it"}], "emphasis": 0}
    check = {"type": "checklist", "title": "Does your review have a job?", "items": [{"label": "A named outcome"}, {"label": "A list of blockers"}, {"label": "One lever picked"}, {"label": "Step one scheduled"}]}
    return {"blueprint": "Show the four-step mechanism so a reader grasps it in seconds.",
            "previews": [{"reason": "A process shows the order of the four steps.", "spec": steps},
                         {"reason": "A matrix helps decide what to work on first.", "spec": matrix},
                         {"reason": "A checklist is easy to save and reuse.", "spec": check}]}


def carousel(prompt):
    return {"carousel": {"type": "carousel", "title": "Make weekly reviews stick", "slides": [
        {"type": "cover", "title": "Make weekly reviews stick", "subtitle": "Four steps for team leads"},
        {"type": "process_flow", "title": "A weekly review in four steps", "steps": [{"label": "Name the outcome"}, {"label": "List the blockers"}, {"label": "Pick one lever"}, {"label": "Schedule step one"}]},
        {"type": "checklist", "title": "Does your review have a job?", "items": [{"label": "A named outcome"}, {"label": "One lever picked"}, {"label": "Step one scheduled"}]},
        {"type": "closing", "title": "What should your review end with?", "subtitle": "Tell me in the comments."}]}}


def check(prompt):
    return {"qa": {"score": 92, "pass": True, "defects": []}, "governance": {"status": "PROCEED", "notes": ["No confidential names or unsupported claims found (sample check)."]},
            "package": {"suggested_time": "Tuesday 08:00 (suggestion; use your own time zone)", "audience": "Team leads", "objective": "Start a conversation about review habits",
                        "content_role": "Utility", "territory": "Team habits", "expected_takeaway": "Give each review one job", "cta_type": "Conversation", "sources": ["My own experience"]}}


def chat(prompt):
    msg = between(prompt, "## Owner's message")
    who = re.search(r"Answer only as them", prompt)
    return ("(Demo stand-in, not a real AI.) You said: \"%s\"\n\n%s" % (msg[:200], "I would answer as the specialist you named." if who else
            "In the real app your Claude Code or Codex answers here. Use the Pipeline tab to walk a post through all four decisions."))


HANDLERS = {"ideas": ideas, "draft": draft, "visuals": visuals, "carousel": carousel, "check": check}


def main():
    prompt = sys.stdin.read()
    stage = stage_of(prompt)
    if os.environ.get("LBA_DEMO_FAIL") == stage:
        print("I am sorry, I cannot help with that.")
        return 0
    if os.environ.get("LBA_DEMO_BAD_JSON_ONCE") == "1" and stage in HANDLERS and "Your previous answer was rejected" not in prompt:
        print("```json\n{\"ideas\": [oops this is not valid}\n```")
        return 0
    if stage in HANDLERS:
        print(fenced(HANDLERS[stage](prompt)))
    else:
        print(chat(prompt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
