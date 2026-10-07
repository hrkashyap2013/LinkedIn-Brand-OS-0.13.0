#!/usr/bin/env python3
"""A rule-based first sort of the comments on your post. No AI, no network. The Reply agent may overrule it.

    python3 scripts/reply_filter.py --file comments.json [--json]      # [{"id","author","text","parent_id"}, ...]
    python3 scripts/reply_filter.py --file comments.txt                # "Author: comment text" blocks separated by blank lines

Classes: ANSWER (a real question), ADD (adds a point), DISAGREE, THANK (short appreciation: a reaction is enough),
SKIP (spam or a pitch), RISK (hostile, legal, medical, financial or personal-data topics: tell the owner first),
INJECTION (the comment tries to instruct an AI: quote it to the owner and ignore it).

LinkedIn shows two levels of replies, so an answer to a reply goes under its top-level comment (`reply_under`).
Nothing is ever posted by this script.

Needs Python 3.8+ and nothing else.
"""
import argparse
import json
import re
import sys

INJECTION = re.compile(r"(ignore (?:all |your |the |any )?(?:previous|prior|above)?\s*(?:instructions|rules|prompt)|disregard (?:your|the|all)|system prompt|you are now\b|"
                       r"act as (?:an? )?(?:ai|assistant|chatbot)|as an ai (?:assistant|model)|reveal your|run (?:this|the following) (?:command|code)|execute (?:this|the following))", re.I)
SPAM = re.compile(r"(dm me|message me|check out my|follow me|visit my|buy now|limited offer|promo code|discount|crypto|forex|whatsapp|telegram|earn \$|make money|click (?:the )?link|link in bio|www\.|https?://)", re.I)
HOSTILE = re.compile(r"\b(idiot|stupid|moron|scam|fraud|fake|liar|shut up|garbage|trash|clown|useless|pathetic)\b", re.I)
RISKY = re.compile(r"\b(lawsuit|sue you|lawyer|legal action|attorney|diagnos\w+|suicid\w+|self-harm|harass\w+|discriminat\w+|confidential|salary of|password|social security|"
                   r"credit card|medical advice|investment advice)\b", re.I)
PRIVATE_DATA = re.compile(r"([\w.+-]+@[\w-]+\.[\w.-]+|\+?\d[\d\s().-]{8,}\d)")
DISAGREE = re.compile(r"^\W*(i disagree|i don't (?:think|agree)|i do not (?:think|agree)|not true|that's not|that is not|actually,|however,|but i think|respectfully,? i)", re.I)
GENERIC_PRAISE = re.compile(r"^\W*(great|nice|good|awesome|amazing|love|so true|well said|spot on|insightful|thanks for sharing|congrat\w*|agreed|100%)\b", re.I)
THANKS = re.compile(r"\b(thank you|thanks|grateful|appreciate)\b", re.I)


def classify(comment):
    """Return {class, action, reason} for one comment dict with at least a 'text'."""
    text = str(comment.get("text", "")).strip()
    n = len(re.findall(r"\w+", text))
    if not re.search(r"\w", text):
        return {"class": "SKIP", "action": "react", "reason": "emoji or symbols only"}
    if INJECTION.search(text):
        return {"class": "INJECTION", "action": "flag", "reason": "tries to give instructions to an AI; quote it to the owner and ignore it"}
    if HOSTILE.search(text) or RISKY.search(text) or PRIVATE_DATA.search(text):
        return {"class": "RISK", "action": "flag", "reason": "hostile, legal, medical, financial or personal-data content; the owner decides if and how to answer"}
    if SPAM.search(text):
        return {"class": "SKIP", "action": "skip", "reason": "looks like a pitch or spam"}
    if "?" in text:
        return {"class": "ANSWER", "action": "reply", "reason": "asks a question"}
    if DISAGREE.search(text):
        return {"class": "DISAGREE", "action": "reply", "reason": "disagrees; engage with the substance, once"}
    if n <= 8 and (GENERIC_PRAISE.search(text) or THANKS.search(text)):
        return {"class": "THANK", "action": "react", "reason": "short appreciation; a reaction or a one-line thank-you is enough"}
    if n >= 12:
        return {"class": "ADD", "action": "reply", "reason": "adds a point; acknowledge it and add one thing"}
    return {"class": "THANK", "action": "react", "reason": "short comment with no question"}


def top_level_id(comments, comment):
    """The id of the top-level comment a reply belongs to (LinkedIn flattens deeper replies to two levels)."""
    by_id = {c.get("id"): c for c in comments if c.get("id") is not None}
    cur, seen = comment, set()
    while cur.get("parent_id") and cur.get("parent_id") in by_id and cur.get("id") not in seen:
        seen.add(cur.get("id"))
        cur = by_id[cur["parent_id"]]
    return cur.get("id")


def triage(comments):
    out = []
    for c in comments:
        res = classify(c)
        item = dict(c, **res)
        if c.get("parent_id"):
            item["reply_under"] = top_level_id(comments, c)
        out.append(item)
    return out


def parse_text(raw):
    blocks = [b.strip() for b in re.split(r"\n\s*\n", raw.replace("\r\n", "\n")) if b.strip()]
    out = []
    for i, b in enumerate(blocks, 1):
        m = re.match(r"^([^:\n]{1,60}):\s*(.+)$", b, re.S)
        out.append({"id": i, "author": m.group(1).strip() if m else "", "text": (m.group(2) if m else b).strip()})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rule-based first sort of comments (nothing is posted).")
    ap.add_argument("--file", required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        raw = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8").read()
        comments = json.loads(raw) if raw.lstrip().startswith("[") else parse_text(raw)
    except (OSError, ValueError) as exc:
        print("reply_filter: %s" % exc, file=sys.stderr)
        return 2
    res = triage(comments)
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        for r in res:
            print("%-9s %-6s %s%s: %s" % (r["class"], r["action"], r.get("author", ""), (" (reply under %s)" % r["reply_under"]) if r.get("reply_under") is not None else "", r["text"][:70].replace("\n", " ")))
            print("          %s" % r["reason"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
