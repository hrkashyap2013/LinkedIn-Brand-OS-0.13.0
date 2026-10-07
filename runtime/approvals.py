#!/usr/bin/env python3
"""The owner's four decisions, recorded in the Approval Log and checked against the exact content.

    python3 scripts/approvals.py list   --post-id P-20261006-01
    python3 scripts/approvals.py verify --post-id P-20261006-01          # exit 0 only if all four match this exact post
    python3 scripts/approvals.py record --post-id P --decision 2 --what "Funnel" --via terminal    # you type APPROVE to confirm
    python3 scripts/approvals.py record --post-id P --decision 3 --what "..." --via chat --quote "yes, approve the post"

Decisions: 1 idea, 2 visual, 3 content (post text + the rendered visual), 4 package.

Each row stores a fingerprint of what was approved (see postkit.py). `verify` recomputes the fingerprints from the
files on disk, so changing one word or one label after approval makes the approval stop matching: nothing can be
packaged for posting until the changed item is approved again.

How a decision gets recorded, and how much that proves:
  app / terminal   the owner clicked Approve in the chat app, or typed APPROVE at a keyboard. A program (not an AI)
                   writes the row, so an AI cannot approve on the owner's behalf.
  chat             an AI assistant recorded what the owner said in a chat. The owner's words are stored in the row.
                   This is only as trustworthy as the assistant relaying them; use the app or terminal for a hard guarantee.

Needs Python 3.8+ and nothing else.
"""
import argparse
import datetime
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import memory_guard as mg  # noqa: E402
import postkit  # noqa: E402

DECISIONS = {1: ("idea", "idea"), 2: ("visual", "visual"), 3: ("content", "content"), 4: ("package", "package")}
VIAS = ("app", "terminal", "chat")


class ApprovalError(ValueError):
    pass


def now_text():
    return datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")


def read_rows(ws):
    """Every row of the Approval Log as a dict keyed by column name."""
    path = os.path.join(ws, "memory", "approval-log.md")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().replace("\r\n", "\n").split("\n")
    tbl = mg.find_table(lines)
    if not tbl:
        return []
    header = mg.split_row(lines[tbl[0]])
    rows = []
    for ln in lines[tbl[0] + 2:tbl[1] + 1]:
        cells = mg.split_row(ln)
        if len(cells) == len(header):
            rows.append(dict(zip(header, cells)))
    return rows


def decision_number(cell):
    cell = str(cell).strip()
    return int(cell[0]) if cell[:1] in "1234" and cell[:1] else None


def decisions_for(ws, post_id):
    """Latest row per decision number for this post: {1: row, ...}."""
    latest = {}
    for row in read_rows(ws):
        if row.get("Post ID", "").strip() == post_id:
            d = decision_number(row.get("Decision", ""))
            if d:
                latest[d] = row
    return latest


def expected_fingerprint(ws, post_id, decision):
    fps = postkit.fingerprints(ws, post_id)
    return fps[DECISIONS[decision][1]]


def verify(ws, post_id):
    """Return (ok, problems). ok is True only if all four decisions exist and match the current content exactly."""
    postkit.check_id(post_id)
    latest = decisions_for(ws, post_id)
    problems = []
    names = {1: "the idea", 2: "the visual", 3: "the content (post text and rendered visual)", 4: "the package"}
    for d in (1, 2, 3, 4):
        row = latest.get(d)
        if row is None:
            problems.append("Decision %d is missing: you have not approved %s." % (d, names[d]))
            continue
        want = expected_fingerprint(ws, post_id, d)
        if want is None:
            if d == 1:
                continue            # a post with no stored idea text can still carry a decision 1 row
            problems.append("Decision %d cannot be checked because %s does not exist on disk yet." % (d, names[d]))
            continue
        got = row.get("Package fingerprint", "").strip()
        if got != "%s:%s" % (DECISIONS[d][0], want):
            problems.append("Decision %d no longer matches: %s changed after you approved it. Approve the new version." % (d, names[d]))
    return (not problems), problems


def record(ws, post_id, decision, what, via, by=None, quote=""):
    """Write one decision row through the write guard. Returns the Entry ID."""
    postkit.check_id(post_id)
    if decision not in DECISIONS:
        raise ApprovalError("decision must be 1, 2, 3 or 4")
    if via not in VIAS:
        raise ApprovalError("via must be one of: %s" % ", ".join(VIAS))
    what = " ".join(str(what).split())[:200]
    if not what:
        raise ApprovalError("say what was approved")
    if via == "chat" and len(" ".join(str(quote).split())) < 2:
        raise ApprovalError("a chat approval must include the owner's own words (--quote)")
    want = expected_fingerprint(ws, post_id, decision)
    if want is None:
        raise ApprovalError("there is nothing on disk to approve for decision %d yet (%s)" % (decision, {
            1: "save the chosen idea first", 2: "save the picked visual first", 3: "render the visual and save the post text first",
            4: "complete the package first"}[decision]))
    if decision == 4:
        ok3, probs = verify_through(ws, post_id, 3)
        if not ok3:
            raise ApprovalError("decision 4 needs decision 3 first. " + " ".join(probs))
    by = by or postkit.owner_name(ws)
    entry_id = "A-%s-D%d-%s" % (post_id[2:], decision, datetime.datetime.now().strftime("%H%M%S"))
    note = {"app": "approved in the chat app", "terminal": "approved by typing APPROVE", "chat": "relayed by an AI assistant from the owner's chat words"}[via]
    if quote:
        note += '; owner said: "%s"' % " ".join(str(quote).split())[:160]
    text = "\n".join(["REGISTER ENTRY", "register: approval-log", "Entry ID: " + entry_id, "Date and time: " + now_text(), "Post ID: " + post_id,
                      "Decision: %d %s" % (decision, DECISIONS[decision][0]), "What was approved: " + what,
                      "Package fingerprint: %s:%s" % (DECISIONS[decision][0], want), "Approved by: " + by, "Notes: " + note]) + "\n"
    r = subprocess.run([sys.executable, os.path.join(HERE, "memory_guard.py"), "--workspace", ws, "apply", "--agent", "orchestrator", "--file", "-"],
                       input=text, capture_output=True, text=True)
    if r.returncode != 0:
        raise ApprovalError("the write guard refused: " + (r.stderr or r.stdout).strip())
    return entry_id


def verify_through(ws, post_id, upto):
    latest = decisions_for(ws, post_id)
    problems = []
    for d in range(1, upto + 1):
        row = latest.get(d)
        want = expected_fingerprint(ws, post_id, d)
        if row is None:
            problems.append("decision %d is missing." % d)
        elif want is not None and row.get("Package fingerprint", "").strip() != "%s:%s" % (DECISIONS[d][0], want):
            problems.append("decision %d no longer matches the current content." % d)
    return (not problems), problems


def main(argv=None):
    ap = argparse.ArgumentParser(description="Record and verify the owner's four decisions.")
    ap.add_argument("--workspace", default=os.path.dirname(HERE))
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("list", "verify"):
        sub.add_parser(name).add_argument("--post-id", required=True)
    r = sub.add_parser("record")
    r.add_argument("--post-id", required=True)
    r.add_argument("--decision", type=int, required=True, choices=[1, 2, 3, 4])
    r.add_argument("--what", required=True)
    r.add_argument("--via", choices=["terminal", "chat"], required=True)
    r.add_argument("--by")
    r.add_argument("--quote", default="")
    a = ap.parse_args(argv)
    ws = os.path.abspath(a.workspace)
    try:
        if a.cmd == "list":
            latest = decisions_for(ws, a.post_id)
            for d in (1, 2, 3, 4):
                row = latest.get(d)
                print("Decision %d: %s" % (d, ("%s (%s, %s)" % (row["What was approved"], row["Date and time"], row["Approved by"])) if row else "not approved"))
            return 0
        if a.cmd == "verify":
            ok, problems = verify(ws, a.post_id)
            print("All four decisions match this exact post." if ok else "NOT approved for posting:")
            for p in problems:
                print("  - " + p)
            return 0 if ok else 1
        if a.via == "terminal":
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                raise ApprovalError("--via terminal needs a person at a keyboard. An AI assistant cannot use it; it may use --via chat with the owner's words.")
            typed = input("Type APPROVE to record decision %d (%s) for %s: " % (a.decision, a.what, a.post_id)).strip()
            if typed != "APPROVE":
                raise ApprovalError("not confirmed; nothing was recorded")
        print("recorded " + record(ws, a.post_id, a.decision, a.what, a.via, a.by, a.quote))
        return 0
    except (ApprovalError, postkit.PostError) as exc:
        print("approvals: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
