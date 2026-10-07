#!/usr/bin/env python3
"""Measures how much a text reads as machine-made, and checks that an edit did not flatten the writer's voice.

    python3 scripts/ai_tells.py --file draft.txt [--tier forensic|strict|style] [--json]
    python3 scripts/ai_tells.py compare --before draft.txt --after edited.txt [--signature "a phrase"] [--json]

Tiers (each includes the ones before it; the default is strict):
  forensic  leftovers no person would write: chatbot lines, placeholders, tracking marks, markdown, many em dashes
  strict    machine patterns judged by density: stock vocabulary clusters, filler bridges, "not X but Y", stacked triads, staccato runs
  style     evenness: uniform sentence length, bold overuse, same-sized paragraphs

The score runs from 0 (nothing found) up to 100. It is a rough guide for editing, not a detector verdict: it cannot tell
who wrote a text and it does not predict how any detector or reader will react.

`compare` is the over-correction guard. It fails an edit that changed or added a figure, a quotation or a link, dropped a
signature phrase, made the sentences more uniform, cut the text by more than a quarter, or left more tells than before.

Needs Python 3.8+ and nothing else.
"""
import argparse
import json
import math
import re
import sys

TIERS = ["forensic", "strict", "style"]
WEIGHT = {"forensic": 8, "strict": 4, "style": 2}

CHATBOT = re.compile(r"\b(certainly[!,.]|absolutely[!,.]|as an ai\b(?: language model)?|i hope this helps|great question|here(?:'s| is) (?:a|the|your) (?:revised|updated|improved|draft)|feel free to|let me know if|i'd be happy to|i would be happy to)", re.I)
PLACEHOLDER = re.compile(r"(\[[A-Z][A-Za-z ]{1,30}\]|\{\{[^}]+\}\}|<insert[^>]*>)")
TRACKING = re.compile(r"(utm_source=(?:chatgpt|openai)[^\s]*|oaicite|turn\d+search\d+|contentReference\[)", re.I)
MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s", re.M)
MD_BOLD = re.compile(r"\*\*[^*\n]+\*\*")
INVISIBLE = re.compile("[\u200b-\u200f\u2060\ufeff]")
VOCAB = ("delve|delving|tapestry|realm|landscape|unlock|unleash|leverage|leveraging|seamless|seamlessly|robust|pivotal|crucial|game-changer|game changer|cutting-edge|"
         "navigate|navigating|testament|intricate|holistic|synergy|elevate|foster|harness|underscore|paradigm|ever-evolving|transformative|revolutionize|streamline|empower|"
         "beacon|multifaceted|embark|journey")
VOCAB_RX = re.compile(r"\b(%s)\b" % VOCAB, re.I)
BRIDGE = re.compile(r"\b(here(?:'s| is) the thing|here(?:'s| is) why|let that sink in|the truth is|let(?:'s| us) dive in|let(?:'s| us) break (?:it|this) down|buckle up|read that again|and here(?:'s| is) the kicker|spoiler:)", re.I)
NEG_PARALLEL = re.compile(r"\b(?:it(?:'s| is)|this is|that(?:'s| is)|you(?:'re| are)) not (?:just |only |about )?[^.,;:\n—]{2,45}[,;—-]\s*(?:it(?:'s| is)|but|you(?:'re| are)|this is)\b", re.I)
TRIAD = re.compile(r"\b[\w-]+(?: [\w-]+)?, [\w-]+(?: [\w-]+)?,? (?:and|or) [\w-]+\b")
STOCK_OPENER = re.compile(r"^\W*(in today(?:'s)?|in a world|in an era|imagine a world|picture this|have you ever wondered|in the (?:ever|fast))", re.I)
STOCK_CLOSER = re.compile(r"^\W*(in conclusion|in summary|to sum up|ultimately,|at the end of the day|the bottom line)", re.I)
HEDGES = re.compile(r"\b(may|might|potentially|perhaps|arguably|possibly|somewhat|relatively)\b", re.I)
NUM_RX = re.compile(r"(?<![\w#])\$?\d[\d,.]*\s?(?:%|k|K|m|M|x|X)?(?![\w])")
QUOTE_RX = re.compile(r"[\"“]([^\"”]{12,200})[\"”]")
URL_RX = re.compile(r"https?://\S+|www\.\S+")


LIST_LINE = re.compile(r"(?m)^\s*(?:\d{1,2}[.)]|[-*\u2022])\s+.*$")


def prose(text):
    """The text without list items: short list lines are not staccato writing and do not count toward sentence rhythm."""
    return LIST_LINE.sub("", text)


def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", prose(text).strip())
    return [p.strip() for p in parts if p.strip() and re.search(r"\w", p)]


def words(text):
    return re.findall(r"\b[\w'-]+\b", text)


def _f(tier, code, message, count=1, examples=None):
    return {"tier": tier, "code": code, "message": message, "count": count, "examples": (examples or [])[:4]}


def analyze(text, tier="strict"):
    if tier not in TIERS:
        raise ValueError("tier must be one of: %s" % ", ".join(TIERS))
    active = TIERS[:TIERS.index(tier) + 1]
    text = (text or "").replace("\r\n", "\n")
    n_words = max(len(words(text)), 1)
    found = []
    if "forensic" in active:
        for rx, code, msg in ((CHATBOT, "CHATBOT_RESIDUE", "Chatbot wording that no person would write"), (PLACEHOLDER, "PLACEHOLDER", "Unfilled placeholder"),
                              (TRACKING, "TRACKING_MARK", "Tracking or citation leftovers from an AI tool"), (INVISIBLE, "INVISIBLE_CHARS", "Invisible characters")):
            hits = [m.group(0) for m in rx.finditer(text)]
            if hits:
                found.append(_f("forensic", code, msg, len(hits), hits))
        if MD_HEADING.search(text):
            found.append(_f("forensic", "MARKDOWN", "Markdown headings do not render on LinkedIn", len(MD_HEADING.findall(text))))
        dashes = text.count("\u2014")
        allowed = max(1, int(n_words / 150.0))
        if dashes > allowed:
            found.append(_f("forensic", "EM_DASHES", "%d em dashes in %d words (about %d is plenty); use full stops or commas" % (dashes, n_words, allowed), dashes))
    if "strict" in active:
        paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        vocab_all = [m.group(0).lower() for m in VOCAB_RX.finditer(text)]
        dense = [p for p in paras if len({m.group(0).lower() for m in VOCAB_RX.finditer(p)}) >= 3]
        if dense or len(vocab_all) / (n_words / 100.0) > 1.5:
            found.append(_f("strict", "AI_VOCABULARY", "Stock vocabulary clustering (judge by density, not single words)", len(vocab_all), sorted(set(vocab_all))))
        bridges = [m.group(0) for m in BRIDGE.finditer(text)]
        if bridges:
            found.append(_f("strict", "FILLER_BRIDGE", "Filler bridges that delay the point", len(bridges), bridges))
        neg = [m.group(0) for m in NEG_PARALLEL.finditer(text)]
        if len(neg) >= 2:
            found.append(_f("strict", "NEGATIVE_PARALLELISM", "\"It is not X, it is Y\" used more than once", len(neg), neg))
        triads = TRIAD.findall(text)
        if len(triads) >= 3:
            found.append(_f("strict", "STACKED_TRIADS", "Three-item lists used again and again", len(triads), triads))
        sents = sentences(text)
        run = best = 0
        for s in sents:
            run = run + 1 if len(words(s)) <= 4 else 0
            best = max(best, run)
        if best >= 3:
            found.append(_f("strict", "STACCATO_RUN", "%d very short sentences in a row" % best, best))
        if sents and STOCK_OPENER.search(sents[0]):
            found.append(_f("strict", "STOCK_OPENER", "A stock opening line", 1, [sents[0][:60]]))
        if len(sents) > 3 and STOCK_CLOSER.search(sents[-1]):
            found.append(_f("strict", "RESTATING_CLOSER", "A closing line that restates the post", 1, [sents[-1][:60]]))
        hedged = [s for s in sents if len(HEDGES.findall(s)) >= 2]
        if hedged:
            found.append(_f("strict", "HEDGE_PILE", "Several hedges in one sentence", len(hedged), [h[:60] for h in hedged]))
    if "style" in active:
        sents = sentences(text)
        lens = [len(words(s)) for s in sents]
        if len(lens) >= 6:
            mean = sum(lens) / float(len(lens))
            sd = math.sqrt(sum((x - mean) ** 2 for x in lens) / len(lens))
            if mean and sd / mean < 0.35:
                found.append(_f("style", "UNIFORM_SENTENCES", "Sentences are very even in length; vary them", 1))
        if len(MD_BOLD.findall(text)) >= 3:
            found.append(_f("style", "BOLD_OVERUSE", "Bold used three or more times", len(MD_BOLD.findall(text))))
        plens = [len(p) for p in re.split(r"\n\s*\n", text) if p.strip()]
        if len(plens) >= 4 and max(plens) <= 1.15 * min(plens):
            found.append(_f("style", "EVEN_PARAGRAPHS", "Paragraphs are all about the same size", 1))
    score = min(100, sum(WEIGHT[f["tier"]] * min(f["count"], 3) for f in found))
    label = "clean" if score < 10 else ("some tells" if score < 30 else "heavy")
    return {"tier": tier, "score": score, "label": label, "findings": found, "words": n_words}


def _numbers(text):
    """Every figure in the text (list numbering such as '1.' at the start of a line is not a figure)."""
    text = re.sub(r"(?m)^\s*\d{1,2}[.)]\s+", "", text)
    return sorted(re.sub(r"\s", "", n).rstrip(".,") for n in NUM_RX.findall(text))


def _sentence_sd(text):
    lens = [len(words(s)) for s in sentences(text)]
    if len(lens) < 3:
        return None
    mean = sum(lens) / float(len(lens))
    return math.sqrt(sum((x - mean) ** 2 for x in lens) / len(lens))


def compare(before, after, signatures=None, tier="strict"):
    """The over-correction guard. Returns {ok, problems, warnings, before, after}."""
    problems, warnings = [], []
    nb, na = _numbers(before), _numbers(after)
    for n in sorted(set(nb) - set(na)):
        problems.append("The figure %s was removed or changed." % n)
    for n in sorted(set(na) - set(nb)):
        problems.append("The figure %s is new; an edit must not add figures." % n)
    for q in QUOTE_RX.findall(before):
        if q not in after:
            problems.append("A quotation was changed or removed: \"%s...\"" % q[:40])
    for u in URL_RX.findall(before):
        if u not in after:
            problems.append("A link was removed or changed: %s" % u)
    for sig in signatures or []:
        if sig and sig.lower() in before.lower() and sig.lower() not in after.lower():
            problems.append("The signature phrase %r was dropped." % sig)
    wb, wa = len(words(before)), len(words(after))
    if wb and wa < 0.75 * wb:
        problems.append("The text got much shorter (%d to %d words). Check that nothing real was cut." % (wb, wa))
    elif wb and wa > 1.25 * wb:
        warnings.append("The text got longer (%d to %d words)." % (wb, wa))
    sb, sa = _sentence_sd(before), _sentence_sd(after)
    if sb and sa is not None and sa < 0.7 * sb:
        problems.append("Sentence length became more uniform (variety fell from %.1f to %.1f). The voice may have been flattened." % (sb, sa))
    rb, ra = analyze(before, tier), analyze(after, tier)
    if ra["score"] > rb["score"]:
        problems.append("The edit left more machine-like patterns (%d) than before (%d)." % (ra["score"], rb["score"]))
    names_b = set(re.findall(r"(?<=[a-z,;] )[A-Z][a-z]{2,}\b", before))
    lost = sorted(n for n in names_b if n not in after)
    if lost:
        warnings.append("Capitalised terms that were in the original are missing: %s." % ", ".join(lost[:5]))
    return {"ok": not problems, "problems": problems, "warnings": warnings, "before": rb["score"], "after": ra["score"]}


def _read(path):
    return sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("check", "compare"):
        argv = ["check"] + argv
    ap = argparse.ArgumentParser(description="Measure machine-like patterns and guard against over-correction.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--file", required=True)
    c.add_argument("--tier", choices=TIERS, default="strict")
    c.add_argument("--json", action="store_true")
    d = sub.add_parser("compare")
    d.add_argument("--before", required=True)
    d.add_argument("--after", required=True)
    d.add_argument("--signature", action="append", default=[])
    d.add_argument("--tier", choices=TIERS, default="strict")
    d.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "check":
            rep = analyze(_read(a.file), a.tier)
            if a.json:
                print(json.dumps(rep, indent=2))
            else:
                print("Machine-like patterns (%s tier): score %d/100, %s" % (rep["tier"], rep["score"], rep["label"]))
                for f in rep["findings"]:
                    print("  [%s] %s x%d: %s%s" % (f["tier"], f["code"], f["count"], f["message"], ("  e.g. " + "; ".join(f["examples"])) if f["examples"] else ""))
            return 0
        rep = compare(_read(a.before), _read(a.after), a.signature, a.tier)
        if a.json:
            print(json.dumps(rep, indent=2))
        else:
            print("Guard: %s (tells %d -> %d)" % ("OK" if rep["ok"] else "PROBLEMS", rep["before"], rep["after"]))
            for p in rep["problems"]:
                print("  PROBLEM: " + p)
            for w in rep["warnings"]:
                print("  note: " + w)
        return 0 if rep["ok"] else 1
    except OSError as exc:
        print("ai_tells: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
