#!/usr/bin/env python3
"""Try the whole system in a few minutes with NO account, NO key and NO cost.

    python3 scripts/demo.py                  # a sample workspace in ~/linkedin-demo, then the browser app
    python3 scripts/demo.py --terminal       # the same, in the terminal
    python3 scripts/demo.py --dir ./my-demo --no-browser

It builds a sample workspace for a fictional coaching business and starts the app with a stand-in "AI" that gives
fixed sample answers. Everything else is real: the visual engine, the checks, your four decisions, the Approval Log
and the ready-to-paste package. Your own workspace is never touched. Nothing is posted anywhere.

(From a clone of the repository you can run it as:  python3 runtime/demo.py)
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MARKER = ".lba-demo"

PROFILE = """# Brand Profile (SAMPLE: a fictional business, for the demo only)

## 1. Owner
- Name: Sample Owner
- Role / title: Founder, Brightpath Coaching
- Field / industry: Team coaching for small companies
- Roles: owner and approver
- Who approves the four decisions: Sample Owner
- Posting language(s): English

## 2. Positioning
- Primary identity: A practical coach for new team leads
- Specialist authority: Weekly rhythms, handovers and meetings
- Brand promise (one sentence): Small habits that make teams calmer and clearer.

## 3. Audience
- Target audience(s): New team leads and small-business managers
- Content objectives: Build trust through practical, honest advice

## 4. Voice
- Core voice: practical, direct, human
- Language rules: plain words, short sentences, no hype
- Avoid: guru posturing, clickbait, engagement bait

## 5. Content taxonomy
- Authority territories: Team habits; Meetings; Handovers

## 11. Visual rules
- Primary color for visuals (hex): #1F3A5F
- Accent color for visuals (hex): #C2410C
- Footer text on every visual: Brightpath Coaching (sample)

## 12. Confidentiality and compliance
- Topics that are off limits: client names, anything about a real employer
"""


def blank_register(text):
    """Keep a register's heading and table header, drop every data row."""
    out, in_table, header_done = [], False, 0
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith("|"):
            in_table = True
            header_done += 1
            if header_done <= 2:
                out.append(line)
            continue
        out.append(line)
    return "\n".join(out)


def find_source():
    """(scripts_dir, root) whether we run from a repository clone (runtime/) or an installed workspace (scripts/)."""
    return HERE, ROOT


def build(dest):
    scripts, root = find_source()
    if os.path.exists(dest):
        if not os.path.exists(os.path.join(dest, MARKER)):
            raise SystemExit("error: %s already exists and is not a demo folder (it has no %s file). Choose another --dir; nothing was changed." % (dest, MARKER))
    for d in ("docs", "memory", "scripts", "runs", "drafts", "inbox", "reports", "exports"):
        os.makedirs(os.path.join(dest, d), exist_ok=True)
    with open(os.path.join(dest, MARKER), "w") as fh:
        fh.write("This folder was made by demo.py and is safe to delete.\n")
    # scripts (including the app folder)
    for dirpath, dirs, files in os.walk(scripts):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        rel = os.path.relpath(dirpath, scripts)
        for f in files:
            if f.endswith(".pyc"):
                continue
            target = os.path.join(dest, "scripts", rel) if rel != "." else os.path.join(dest, "scripts")
            os.makedirs(target, exist_ok=True)
            shutil.copy(os.path.join(dirpath, f), os.path.join(target, f))
    for src, dst in (("prompts", "prompts"), (".claude", ".claude")):
        if os.path.isdir(os.path.join(root, src)):
            shutil.copytree(os.path.join(root, src), os.path.join(dest, dst), dirs_exist_ok=True)
    memdir = os.path.join(root, "memory")
    for f in os.listdir(memdir) if os.path.isdir(memdir) else []:
        target = os.path.join(dest, "memory", f)
        if os.path.exists(target):
            continue                                         # keep the demo's own history on a second run
        with open(os.path.join(memdir, f), encoding="utf-8") as fh:
            text = fh.read()
        with open(target, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(blank_register(text) if f.endswith(".md") else text)
    for f in ("metrics-columns.json",):
        if os.path.exists(os.path.join(root, "docs", f)):
            shutil.copy(os.path.join(root, "docs", f), os.path.join(dest, "docs", f))
    with open(os.path.join(dest, "docs", "brand-profile.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(PROFILE)
    with open(os.path.join(dest, "docs", "schedule.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"paused": False, "paused_until": None, "publish_utc_offset": "+00:00", "prep_lead_hours": 12,
                   "slots": [{"day": "Tue", "time": "08:00", "role": "Utility"}, {"day": "Thu", "time": "08:00", "role": "Conversation"}]}, fh, indent=2)
    with open(os.path.join(dest, "docs", "settings.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"setup_completed": True, "language": "English", "posting_languages": ["English"], "users": ["Sample Owner"], "run_tool": "claude",
                   "image_provider": "None (I make or upload visuals myself)", "posting_tool": "I post manually", "notifications": {"desktop": False, "phone": False,
                                                                                                                           "phone_server": "https://ntfy.sh"}}, fh, indent=2)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Try the whole system with a stand-in AI: no account, no key, no cost.")
    ap.add_argument("--dir", default=os.path.join(os.path.expanduser("~"), "linkedin-demo"))
    ap.add_argument("--terminal", action="store_true", help="use the terminal app instead of the browser")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--build-only", action="store_true", help="only create the sample workspace")
    a = ap.parse_args(argv)
    dest = os.path.abspath(a.dir)
    build(dest)
    print("Demo workspace ready: %s" % dest)
    if a.build_only:
        return 0
    sys.path.insert(0, os.path.join(dest, "scripts"))
    if a.terminal:
        import chat_cli
        return chat_cli.main(["--workspace", dest, "--demo"])
    import chat_app
    return chat_app.main(["--workspace", dest, "--demo"] + (["--no-browser"] if a.no_browser else []))


if __name__ == "__main__":
    sys.exit(main())
