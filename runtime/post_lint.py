#!/usr/bin/env python3
"""Checks a post draft for common writing and hygiene problems, with no AI and no network.

    python3 scripts/post_lint.py --file draft.txt          # human-readable report; exit code 1 if there is an ERROR
    python3 scripts/post_lint.py --file draft.txt --json

Levels:  ERROR   fix before approving (empty text, leftover placeholders)
         WARNING a pattern that usually weakens a post or can look like engagement bait
         NOTE    something to look at (figures to back with evidence, very long paragraphs)

These are style and hygiene rules, not predictions: nothing here says a post will or will not perform.

Needs Python 3.8+ and nothing else.
"""
import argparse
import json
import re
import sys

POST_LIMIT = 3000          # LinkedIn commonly allows about this many characters in a post; check your own tool's limit
FIRST_LINE_LIMIT = 150     # our own style rule: the first line should be short enough to read at a glance
HASHTAG_LIMIT = 5          # our own style rule

CANDOR = re.compile(r"\b(honestly|to be honest|let me be honest|full transparency|frankly|unpopular opinion|hot take)\b", re.I)
BAIT = [
    (re.compile(r"\bcomment\s+[\"'“]?[A-Za-z0-9]{2,15}[\"'”]?\s+(?:below\s+)?(?:and|to)\s+(?:i|get|receive)\b", re.I), "asks for a comment in exchange for something"),
    (re.compile(r"\btag\s+(?:a\s+friend|someone|a\s+colleague|three|2|3)\b", re.I), "asks readers to tag others"),
    (re.compile(r"\b(?:repost|reshare|share)\s+if\b", re.I), "asks for a repost"),
    (re.compile(r"\blike\s+if\s+you\b", re.I), "asks for a like"),
    (re.compile(r"\bcomment\s+(?:yes|below|your\s+thoughts)\b", re.I), "asks for a bare comment"),
]
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B06\u2705]")
PLACEHOLDER = re.compile(r"(\[[A-Z][A-Za-z ]{1,30}\]|\{\{[^}]+\}\}|\bTODO\b|\bTBD\b|lorem ipsum|<insert[^>]*>)", re.I)
NUMBER = re.compile(r"(?<![\w#])\$?\d[\d,.]*\s?(?:%|k|K|m|M|x|X)?(?![\w])")


def _finding(level, code, message):
    return {"level": level, "code": code, "message": message}


def lint(text):
    """Return {ok, findings, stats} for one post text."""
    findings = []
    body = (text or "").replace("\r\n", "\n").strip()
    if not body:
        return {"ok": False, "findings": [_finding("ERROR", "EMPTY", "The post text is empty.")], "stats": {"chars": 0, "words": 0}}
    lines = [ln for ln in body.split("\n")]
    first = next((ln.strip() for ln in lines if ln.strip()), "")
    last = next((ln.strip() for ln in reversed(lines) if ln.strip()), "")

    m = PLACEHOLDER.search(body)
    if m:
        findings.append(_finding("ERROR", "PLACEHOLDER", "Leftover placeholder text: %r. Replace it with the real content." % m.group(0)))
    if len(body) > POST_LIMIT:
        findings.append(_finding("WARNING", "TOO_LONG", "The post is %d characters, over the roughly %d LinkedIn commonly allows. Check your tool's limit." % (len(body), POST_LIMIT)))
    letters = [c for c in first if c.isalpha()]
    if len(letters) >= 8 and sum(c.isupper() for c in letters) / float(len(letters)) > 0.7:
        findings.append(_finding("WARNING", "SHOUTING_OPENER", "The first line is mostly capital letters. Say it in a normal voice."))
    if len(first) > FIRST_LINE_LIMIT:
        findings.append(_finding("WARNING", "LONG_FIRST_LINE", "The first line is %d characters. The opening should be short enough to take in at a glance." % len(first)))
    if first.endswith("?"):
        findings.append(_finding("NOTE", "QUESTION_OPENER", "The post opens with a question. Make sure the answer is worth the reader's time."))
    c = CANDOR.search(body)
    if c:
        findings.append(_finding("WARNING", "ANNOUNCED_CANDOR", "Announcing honesty (%r) tends to weaken it. Just say the thing." % c.group(0)))
    if re.search(r"https?://|www\.", body):
        findings.append(_finding("WARNING", "LINK_IN_BODY", "There is a link in the post body. Common advice (unverified) is to put outside links in the first comment; test it with your own results."))
    tags = re.findall(r"(?<!\w)#\w+", body)
    if len(tags) > HASHTAG_LIMIT:
        findings.append(_finding("WARNING", "TOO_MANY_HASHTAGS", "%d hashtags. A few relevant ones are enough." % len(tags)))
    for rx, what in BAIT:
        if rx.search(body):
            findings.append(_finding("WARNING", "ENGAGEMENT_TACTIC", "Use with care: the post %s. Only keep it if it is honest and you deliver on it; Governance should note it." % what))
    if re.fullmatch(r"(?i)(agree|thoughts|right|do you agree|what do you think)\??\s*[?!.]*", last):
        findings.append(_finding("WARNING", "BAIT_CLOSER", "The closing line (%r) is only a vote. Ask a real question about the topic instead." % last))
    if re.search(r"^\s{0,3}#{1,6}\s", body, re.M):
        findings.append(_finding("WARNING", "MARKDOWN_HEADING", "A markdown heading (#) will show as plain characters on LinkedIn."))
    if len(EMOJI.findall(body)) > 5:
        findings.append(_finding("WARNING", "EMOJI_HEAVY", "More than five emoji. They compete with the words."))
    shouted = [w for w in re.findall(r"\b[A-Z]{4,}\b", body) if w not in ("HTTP", "HTTPS", "UTC", "NASA", "USA")]
    if len(shouted) > 3:
        findings.append(_finding("WARNING", "ALL_CAPS_WORDS", "Several words in all capitals (%s ...). Use them sparingly." % ", ".join(shouted[:3])))
    unlisted = re.sub(r"(?m)^\s*\d{1,2}[.)]\s+", "", body)                   # list numbering such as "1." at a line start is not a figure
    nums = [n.strip().rstrip(".,") for n in NUMBER.findall(unlisted) if re.search(r"\d", n)]
    if nums:
        findings.append(_finding("NOTE", "FIGURES", "The post contains %d figure(s) (%s). Confirm each has OWNER DATA or SOURCED support." % (len(nums), ", ".join(nums[:8]))))
    for para in [p for p in re.split(r"\n\s*\n", body) if p.strip()]:
        if len(para) > 600:
            findings.append(_finding("NOTE", "LONG_PARAGRAPH", "A paragraph is %d characters long. Consider breaking it up." % len(para)))
            break
    words = len(re.findall(r"\b\w+\b", body))
    stats = {"chars": len(body), "words": words, "lines": len([ln for ln in lines if ln.strip()]), "hashtags": len(tags), "links": len(re.findall(r"https?://|www\.", body))}
    return {"ok": not any(f["level"] == "ERROR" for f in findings), "findings": findings, "stats": stats}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lint a post draft (no AI, no network).")
    ap.add_argument("--file", required=True, help="the draft text file (use - for standard input)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        text = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8").read()
    except OSError as exc:
        print("post_lint: %s" % exc, file=sys.stderr)
        return 2
    rep = lint(text)
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        s = rep["stats"]
        print("%d characters, %d words" % (s["chars"], s["words"]))
        for f in rep["findings"]:
            print("%-7s %-18s %s" % (f["level"], f["code"], f["message"]))
        if not rep["findings"]:
            print("No findings.")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
