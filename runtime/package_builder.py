#!/usr/bin/env python3
"""Builds the ready-to-paste package for an approved post. This is the "posting script": it never posts anywhere.

    python3 scripts/package_builder.py check --id P-20261006-01     # is everything approved and complete? changes nothing
    python3 scripts/package_builder.py build --id P-20261006-01     # makes exports/ready-to-paste/P-20261006-01/

It refuses to build unless all four of your decisions are in the Approval Log AND still match the exact
post text, visual, alt text and every package field on disk. Edit one word after approving and it stops
until you approve the new version.

The package folder holds, ready to copy:
    PACKAGE.md          everything in order, with the exact text in boxes you can copy
    post.txt            the post text
    first-comment.txt   the first comment (post it right after you publish)
    pin-comment.txt     the comment to pin
    suggested-time.txt  when to post
    visual.png / .pdf / .svg, alt-text.txt, visual-prompt.txt
    MANIFEST.json       fingerprints of everything, so you can prove it is the approved version

You then post it yourself in LinkedIn or in your scheduler tool. After posting, run `/live` (or the app's
"Mark as live" button) to start your results-check reminders.

Needs Python 3.8+ and nothing else.
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import approvals  # noqa: E402
import postkit  # noqa: E402
import visual_engine as ve  # noqa: E402

POST_SOFT_LIMIT = 3000       # LinkedIn commonly allows about 3,000 characters in a post; check your tool's own limit
COMMENT_SOFT_LIMIT = 1250    # and about 1,250 in a comment


class BuildError(ValueError):
    pass


def check(ws, post_id):
    """Return (ok, errors, warnings). Errors block the build; warnings are shown but do not."""
    errors, warnings = [], []
    st = postkit.status(ws, post_id)
    errors += ["Missing: " + m for m in st["missing"]]
    ok_appr, problems = approvals.verify(ws, post_id)
    errors += problems
    pkg = postkit.load_package(ws, post_id)
    text = postkit.read_text(ws, post_id)
    if len(text) > POST_SOFT_LIMIT:
        warnings.append("The post is %d characters. LinkedIn commonly limits posts to about %d; check your tool's limit." % (len(text), POST_SOFT_LIMIT))
    for key, label in (("first_comment", "first comment"), ("pin_comment", "pinned comment")):
        if len(pkg.get(key, "")) > COMMENT_SOFT_LIMIT:
            warnings.append("The %s is %d characters. Comments are commonly limited to about %d." % (label, len(pkg[key]), COMMENT_SOFT_LIMIT))
    if not pkg.get("first_comment"):
        warnings.append("There is no first comment.")
    if not st["files"]["final_png"] and not st["files"]["final_pdf"]:
        warnings.append("Only the SVG exists. LinkedIn needs a PNG or PDF: install Chrome or Edge and run `postkit.py render` again, or export the SVG yourself.")
    meta = postkit.read_json(os.path.join(postkit.post_dir(ws, post_id), "final", "visual.meta.json"), {}) or {}
    for w in meta.get("warnings", []):
        warnings.append("Visual: " + w["message"])
    return (not errors), errors, warnings


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def box(text):
    fence = "```"
    while fence in text:
        fence += "`"
    return "%s\n%s\n%s" % (fence, text.rstrip(), fence)


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")


def build(ws, post_id, track=True, out_dir=None):
    ok, errors, warnings = check(ws, post_id)
    if not ok:
        raise BuildError("This post is not approved for packaging:\n  - " + "\n  - ".join(errors))
    pkg = postkit.load_package(ws, post_id)
    d = postkit.post_dir(ws, post_id)
    fin = os.path.join(d, "final")
    fps = postkit.fingerprints(ws, post_id)
    meta = postkit.read_json(os.path.join(fin, "visual.meta.json"), {})
    out = out_dir or os.path.join(ws, "exports", "ready-to-paste", post_id)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    text = postkit.read_text(ws, post_id)
    write(os.path.join(out, "post.txt"), text.rstrip("\n"))
    write(os.path.join(out, "first-comment.txt"), pkg.get("first_comment", ""))
    write(os.path.join(out, "pin-comment.txt"), pkg.get("pin_comment", ""))
    write(os.path.join(out, "suggested-time.txt"), pkg.get("suggested_time", ""))
    alt = "SHORT\n%s\n\nFULL\n%s" % (meta.get("alt_short", ""), meta.get("alt_long", ""))
    write(os.path.join(out, "alt-text.txt"), alt)
    prompt_src = os.path.join(fin, "visual.prompt.txt")
    prompt = pkg.get("visual_prompt") or (postkit._read(prompt_src) if os.path.exists(prompt_src) else "")
    write(os.path.join(out, "visual-prompt.txt"), prompt)
    copied = []
    for f in sorted(os.listdir(fin)):
        if f.startswith("visual") and f.endswith((".png", ".pdf", ".svg")):
            shutil.copyfile(os.path.join(fin, f), os.path.join(out, f))
            copied.append(f)
    hashtags = " ".join(h if h.startswith("#") else "#" + h for h in pkg.get("hashtags", []))
    main_file = next((f for f in copied if f.endswith(".png")), None) or next((f for f in copied if f.endswith(".pdf")), None) or (copied[0] if copied else "")
    L = ["# Ready to post: %s" % (pkg.get("title") or post_id), "",
         "Post ID: %s. Status: **APPROVED**. All four of your decisions match this exact content (package fingerprint `%s`)." % (post_id, fps["package"]), "",
         "Nothing has been posted. Copy each part below into LinkedIn or your scheduler tool.", "",
         "## 1. Suggested time", pkg.get("suggested_time") or "(none set)", "",
         "## 2. Post text (paste this)", box(text), "",
         "## 3. Visual (upload this file)", "`%s`%s" % (main_file, "  (also: %s)" % ", ".join("`%s`" % f for f in copied if f != main_file) if len(copied) > 1 else ""), "",
         "### Alt text (paste into the image's alt-text field)", box(meta.get("alt_short", "")), "", "Longer description, if your tool allows it:", box(meta.get("alt_long", "")), ""]
    n = 4
    if pkg.get("first_comment"):
        L += ["## %d. First comment (post it right after you publish)" % n, box(pkg["first_comment"]), ""]
        n += 1
    if pkg.get("pin_comment"):
        L += ["## %d. Comment to pin" % n, box(pkg["pin_comment"]), ""]
        n += 1
    if pkg.get("link_comment"):
        L += ["## %d. Link comment" % n, box(pkg["link_comment"]), ""]
        n += 1
    if hashtags or pkg.get("mentions"):
        L += ["## %d. Hashtags and mentions" % n, hashtags or "(no hashtags)"] + ([" ".join(pkg["mentions"])] if pkg.get("mentions") else []) + [""]
        n += 1
    if pkg.get("reply_starters"):
        L += ["## %d. Reply starters (for likely comments; adapt them, do not paste blindly)" % n] + ["- " + r for r in pkg["reply_starters"]] + [""]
        n += 1
    L += ["## %d. Visual prompt (to recreate the visual in a design tool)" % n, box(prompt), ""]
    n += 1
    details = [("Call to action", pkg.get("cta_type")), ("Audience", pkg.get("audience")), ("Objective", pkg.get("objective")),
               ("Content role", pkg.get("content_role")), ("Territory / cluster", pkg.get("territory")), ("Expected takeaway", pkg.get("expected_takeaway")),
               ("Experiment", pkg.get("experiment_id"))]
    details = [(k, v) for k, v in details if v]
    if details:
        L += ["## %d. Why this post" % n] + ["- %s: %s" % kv for kv in details] + [""]
        n += 1
    if pkg.get("sources"):
        L += ["## %d. Sources and attribution" % n] + ["- " + s for s in pkg["sources"]] + [""]
        n += 1
    L += ["## Posting checklist",
          "- [ ] Paste the post text and attach the visual; add the alt text.",
          "- [ ] Check the preview on your phone (nothing cut off, the visual is readable).",
          "- [ ] Publish or schedule at the suggested time (or your own time).",
          "- [ ] Post the first comment; pin the comment if you wrote one.",
          "- [ ] Tell the system it is live (`/live`, or the app's **Mark as live** button) so your results-check reminders (%s) start." % ", ".join(pkg.get("measurement_windows", [])),
          "- [ ] Do not edit the post after publishing without telling me, so measurement stays tied to what was approved.", ""]
    if warnings:
        L += ["## Notes"] + ["- " + w for w in warnings] + [""]
    write(os.path.join(out, "PACKAGE.md"), "\n".join(L))
    manifest = {"post_id": post_id, "built": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "fingerprints": fps,
                "files": {f: sha(os.path.join(out, f)) for f in sorted(os.listdir(out)) if f != "MANIFEST.json"}, "warnings": warnings}
    write(os.path.join(out, "MANIFEST.json"), json.dumps(manifest, indent=2))
    tracked = None
    if track:
        decs = approvals.decisions_for(ws, post_id)
        date = lambda n: (decs[n]["Date and time"].split(" ")[0] if n in decs else "")
        ok_t, msg = postkit.tracker_entry(ws, {
            "Post ID": post_id, "Date created": pkg.get("created", ""), "Topic": pkg.get("title", ""), "Role": pkg.get("role", ""), "Status": "package ready",
            "Decision 1 date": date(1), "Decision 2 date": date(2), "Decision 3 date": date(3), "Decision 4 date": date(4),
            "Scheduler tool": postkit.settings(ws).get("posting_tool", ""), "Scheduled for": pkg.get("suggested_time", ""),
            "Measurement windows": ", ".join(pkg.get("measurement_windows", []))})
        tracked = ok_t
    return {"folder": out, "files": sorted(os.listdir(out)), "warnings": warnings, "tracker_written": tracked}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the ready-to-paste package for an approved post.")
    ap.add_argument("--workspace", default=os.path.dirname(HERE))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("--id", required=True)
    b = sub.add_parser("build")
    b.add_argument("--id", required=True)
    b.add_argument("--no-track", action="store_true", help="do not add a Post Tracker row")
    b.add_argument("--out")
    a = ap.parse_args(argv)
    ws = os.path.abspath(a.workspace)
    try:
        if a.cmd == "check":
            ok, errors, warnings = check(ws, a.id)
            print("READY: all four decisions match and the package is complete." if ok else "NOT READY:")
            for e in errors:
                print("  - " + e)
            for w in warnings:
                print("  note: " + w)
            return 0 if ok else 1
        res = build(ws, a.id, not a.no_track, a.out)
        print("Package built: %s" % res["folder"])
        for f in res["files"]:
            print("  " + f)
        for w in res["warnings"]:
            print("note: " + w)
        if res["tracker_written"] is False:
            print("note: the Post Tracker row could not be written (run `python3 scripts/memory_guard.py check`).")
        print("Nothing was posted. Open PACKAGE.md and copy each part.")
        return 0
    except (BuildError, postkit.PostError, approvals.ApprovalError) as exc:
        print("package_builder: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
