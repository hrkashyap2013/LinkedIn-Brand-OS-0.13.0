#!/usr/bin/env python3
"""Turn a LinkedIn analytics CSV export into the 6-panel dashboard (markdown).

    python3 scripts/metrics.py export.csv [--map docs/metrics-columns.json] [--out reports]

- Uses only the numbers in your file. A missing column leaves its panel entry blank.
- Per-1,000-impression metrics use: (count / impressions) x 1000.
- Medians are shown first (median-first interpretation). There is no combined growth score.
- Column names differ between exports: put the real header text in docs/metrics-columns.json.
Needs Python 3.8+ and nothing else.
"""
import argparse, csv, json, os, statistics, sys
from datetime import date

FIELDS = ["post_id", "date", "title", "impressions", "members_reached", "reactions", "comments",
          "reposts", "saves", "sends", "profile_views", "followers_gained", "link_clicks",
          "search_appearances", "out_of_network_pct"]
ALIASES = {  # plain-English guesses, matched case-insensitively; override in the map file
    "post_id": ["post id", "id", "post"], "date": ["date", "published", "post date"],
    "title": ["title", "post title", "name"], "impressions": ["impressions", "impression"],
    "members_reached": ["members reached", "reach", "unique impressions"],
    "reactions": ["reactions", "likes"], "comments": ["comments"], "reposts": ["reposts", "shares"],
    "saves": ["saves", "saved"], "sends": ["sends", "send"], "profile_views": ["profile views", "profile viewers"],
    "followers_gained": ["followers gained", "new followers", "followers"],
    "link_clicks": ["link clicks", "clicks"], "search_appearances": ["search appearances"],
    "out_of_network_pct": ["out of network %", "out-of-network %", "non-follower %"],
}

def num(v):
    if v is None: return None
    v = str(v).strip().replace(",", "").replace("%", "")
    if v == "" or v.lower() in ("na", "n/a", "-", "null"): return None
    try: return float(v)
    except ValueError: return None

def per1k(count, imp):
    return None if count is None or not imp else count / imp * 1000

def median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None

def fmt(x, d=1):
    return "" if x is None else (f"{x:,.{d}f}" if d else f"{x:,.0f}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_file"); ap.add_argument("--map", default="docs/metrics-columns.json")
    ap.add_argument("--out", default="reports")
    a = ap.parse_args()

    mapping = {}
    if os.path.exists(a.map):
        try: mapping = {k: v for k, v in json.load(open(a.map)).items() if v and not k.startswith("_")}
        except Exception as e: sys.exit(f"cannot read {a.map}: {e}")

    with open(a.csv_file, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows: sys.exit("the CSV has no data rows")
    headers = {h.strip().lower(): h for h in rows[0].keys() if h}
    col = {}
    for fld in FIELDS:
        if fld in mapping and mapping[fld] in rows[0]: col[fld] = mapping[fld]
        elif fld in mapping: sys.exit(f'docs/metrics-columns.json maps {fld} to "{mapping[fld]}" which is not in the CSV')
        else:
            for al in [fld.replace("_", " ")] + ALIASES.get(fld, []):
                if al in headers: col[fld] = headers[al]; break
    missing = [f for f in FIELDS if f not in col]

    posts = []
    for r in rows:
        p = {f: (r.get(col[f]) if f in col else None) for f in FIELDS}
        for f in FIELDS[3:]: p[f] = num(p[f])
        imp = p["impressions"]
        p["fol_1k"] = per1k(p["followers_gained"], imp); p["pv_1k"] = per1k(p["profile_views"], imp)
        p["saves_1k"] = per1k(p["saves"], imp); p["reposts_1k"] = per1k(p["reposts"], imp)
        p["sends_1k"] = per1k(p["sends"], imp)
        pv, fg = p["profile_views"], p["followers_gained"]
        p["p2f"] = (fg / pv * 100) if (pv and fg is not None) else None
        posts.append(p)

    M = lambda k: median([p[k] for p in posts])
    L = []
    L += [f"# Dashboard ({date.today().isoformat()})", "",
          f"Source: `{os.path.basename(a.csv_file)}` | posts: {len(posts)} | median-first, no combined growth score.", ""]
    if len(posts) < 5:
        L += [f"Note: only {len(posts)} post(s). Medians over so few posts are weak evidence; treat any pattern as `INSUFFICIENT EVIDENCE` until more data exists.", ""]
    if missing:
        L += ["Columns not found in this export (their entries are blank, not estimated): " + ", ".join(missing), ""]
    L += ["## Panel 1 - Reach", f"- Median impressions: {fmt(M('impressions'),0)}",
          f"- Median members reached: {fmt(M('members_reached'),0)}",
          f"- Median out-of-network %: {fmt(M('out_of_network_pct'))}", "",
          "## Panel 2 - Authority / Utility",
          f"- Median saves: {fmt(M('saves'),0)} | reposts: {fmt(M('reposts'),0)} | sends: {fmt(M('sends'),0)} | comments: {fmt(M('comments'),0)}",
          f"- Median per 1K impressions: saves {fmt(M('saves_1k'))} | reposts {fmt(M('reposts_1k'))} | sends {fmt(M('sends_1k'))}",
          "- Comment quality is a qualitative judgment: assess it separately.", "",
          "## Panel 3 - Discovery",
          f"- Median profile views: {fmt(M('profile_views'),0)} | search appearances: {fmt(M('search_appearances'),0)} | link clicks: {fmt(M('link_clicks'),0)}", "",
          "## Panel 4 - Follower efficiency",
          f"- Median followers gained: {fmt(M('followers_gained'),0)}",
          f"- Median followers per 1,000 impressions: {fmt(M('fol_1k'),2)}",
          f"- Median profile-to-follow proxy %: {fmt(M('p2f'),2)} (a proxy, not proof of causal conversion)", "",
          "## Panel 5 - Audience quality",
          "- Needs your audience-demographics export (seniority, function, industry). Not computed here.", "",
          "## Panel 6 - Learning",
          "- Fill from Experiment Register decisions and the weekly or monthly review. `INSUFFICIENT EVIDENCE` is a valid outcome.", "",
          "## Per post", "",
          "| Post | Date | Impr. | Fol/1K | PV/1K | Saves/1K | Reposts/1K | Sends/1K |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for p in posts:
        name = (p["title"] or p["post_id"] or "")[:40]
        L.append(f"| {name} | {p['date'] or ''} | {fmt(p['impressions'],0)} | {fmt(p['fol_1k'],2)} | {fmt(p['pv_1k'],2)} | {fmt(p['saves_1k'])} | {fmt(p['reposts_1k'])} | {fmt(p['sends_1k'])} |")
    L += ["", "Attribution wording: say \"LinkedIn reports X new followers from this post's activity\" or \"this post achieved Y followers per 1,000 impressions\". Never \"this post caused X followers\"."]
    text = "\n".join(L) + "\n"
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, f"dashboard-{date.today().isoformat()}.md")
    open(path, "w", encoding="utf-8").write(text)
    print(text); print(f"Saved: {path}")

if __name__ == "__main__":
    main()
