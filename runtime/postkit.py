#!/usr/bin/env python3
"""Everything about one post's files: the folder, the package fields, the visual, and the fingerprints
that tie the owner's approvals to the exact content.

    python3 scripts/postkit.py new --title "Why onboarding fails" [--role Authority]
    python3 scripts/postkit.py text --id P-20261006-01 < post.txt            # saves the post text
    python3 scripts/postkit.py set --id P-20261006-01 --json fields.json     # first comment, pin comment, time, hashtags ...
    python3 scripts/postkit.py visual-spec --id P-20261006-01 --file spec.json
    python3 scripts/postkit.py render --id P-20261006-01 [--format portrait|square|carousel]
    python3 scripts/postkit.py status --id P-20261006-01
    python3 scripts/postkit.py fingerprint --id P-20261006-01
    python3 scripts/postkit.py live --id P-20261006-01 --url https://... --windows 24h,72h,7d
    python3 scripts/postkit.py list

A post lives in drafts/<post-id>/:
    package.json        the fields below (first comment, pin comment, suggested time, hashtags, ...)
    post.txt            the post text
    visual-spec.json    the owner's picked visual (what the visual engine renders)
    previews/           the 3 previews the owner chose from
    final/              the rendered visual (SVG, PNG, PDF, alt text, prompt, meta)

Fingerprints (a short hash of exact content) are what the Approval Log stores:
    idea      the chosen idea
    visual    the picked visual spec
    content   post text + alt text + the visual's SVG files   (decision 3)
    package   every package field + the content fingerprint   (decision 4)
Change one word and the fingerprint changes, so an old approval can never cover new content.

Needs Python 3.8+ and nothing else.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reminders  # noqa: E402
import visual_engine as ve  # noqa: E402

POST_ID = re.compile(r"^P-\d{8}-\d{2,3}$")
STR_FIELDS = ["title", "role", "suggested_time", "first_comment", "pin_comment", "link_comment", "cta_type", "audience", "objective",
              "content_role", "territory", "expected_takeaway", "experiment_id", "visual_prompt", "notes"]
LIST_FIELDS = ["hashtags", "mentions", "reply_starters", "sources", "measurement_windows"]
VOLATILE = ("created", "built", "notes")        # changing these never needs a new approval
MAX_TEXT = 6000


class PostError(ValueError):
    pass


def check_id(post_id):
    if not POST_ID.match(str(post_id or "")):
        raise PostError("post ID %r looks wrong; expected something like P-20261006-01" % (post_id,))
    return post_id


def post_dir(ws, post_id):
    return os.path.join(ws, "drafts", check_id(post_id))


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    _write(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def fp(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def norm_text(text):
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip() + "\n"


def settings(ws):
    return read_json(os.path.join(ws, "docs", "settings.json"), {}) or {}


def owner_name(ws):
    users = settings(ws).get("users") or []
    return users[0] if users else "Owner"


# ----------------------------------------------------------------- files

def blank_package(post_id, title="", role=""):
    pkg = {"post_id": post_id, "created": datetime.date.today().isoformat()}
    for k in STR_FIELDS:
        pkg[k] = ""
    for k in LIST_FIELDS:
        pkg[k] = []
    pkg.update({"title": title, "role": role, "idea": {"title": "", "angle": ""}, "measurement_windows": ["24h", "72h", "7d"]})
    return pkg


def new_post(ws, title, role=""):
    day = datetime.date.today().strftime("%Y%m%d")
    n = 1
    while os.path.exists(os.path.join(ws, "drafts", "P-%s-%02d" % (day, n))):
        n += 1
    post_id = "P-%s-%02d" % (day, n)
    os.makedirs(os.path.join(post_dir(ws, post_id), "final"), exist_ok=True)
    write_json(os.path.join(post_dir(ws, post_id), "package.json"), blank_package(post_id, clean_line(title), clean_line(role)))
    return post_id


def clean_line(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()[:300]


def load_package(ws, post_id):
    pkg = read_json(os.path.join(post_dir(ws, post_id), "package.json"))
    if pkg is None:
        raise PostError("no package for %s; create it with: postkit.py new --title ..." % post_id)
    return pkg


def set_fields(ws, post_id, updates):
    """Merge package fields. Unknown names and wrong shapes are rejected, never silently dropped."""
    pkg = load_package(ws, post_id)
    if not isinstance(updates, dict):
        raise PostError("fields must be a JSON object")
    for k, v in updates.items():
        if k in STR_FIELDS:
            if not isinstance(v, str):
                raise PostError("%s must be text" % k)
            if len(v) > MAX_TEXT:
                raise PostError("%s is too long (%d characters; the limit here is %d)" % (k, len(v), MAX_TEXT))
            pkg[k] = v.replace("\r\n", "\n").strip()
        elif k in LIST_FIELDS:
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                raise PostError("%s must be a list of text items" % k)
            if k == "measurement_windows":
                v = reminders.parse_windows(",".join(v))
            pkg[k] = [x.strip() for x in v if x.strip()]
        elif k == "idea":
            if not isinstance(v, dict):
                raise PostError("idea must be {title, angle}")
            pkg["idea"] = {"title": clean_line(v.get("title", "")), "angle": clean_line(v.get("angle", ""))[:600]}
        else:
            raise PostError("unknown field %r. Known: %s, idea" % (k, ", ".join(STR_FIELDS + LIST_FIELDS)))
    write_json(os.path.join(post_dir(ws, post_id), "package.json"), pkg)
    return pkg


def save_text(ws, post_id, text):
    check_id(post_id)
    load_package(ws, post_id)
    if len(text) > MAX_TEXT:
        raise PostError("the post text is too long (%d characters)" % len(text))
    if not text.strip():
        raise PostError("the post text is empty")
    _write(os.path.join(post_dir(ws, post_id), "post.txt"), norm_text(text))


def read_text(ws, post_id):
    p = os.path.join(post_dir(ws, post_id), "post.txt")
    return _read(p) if os.path.exists(p) else ""


def save_visual_spec(ws, post_id, spec):
    errs = ve.validate_spec(spec)
    if errs:
        raise PostError("the visual spec is not valid: " + "; ".join(errs))
    write_json(os.path.join(post_dir(ws, post_id), "visual-spec.json"), spec)
    return ve.spec_hash(spec)


def load_visual_spec(ws, post_id):
    return read_json(os.path.join(post_dir(ws, post_id), "visual-spec.json"))


def render_final(ws, post_id, fmt="portrait", png=True, pdf=False):
    spec = load_visual_spec(ws, post_id)
    if spec is None:
        raise PostError("no visual has been picked for %s yet" % post_id)
    theme, tw = ve.load_theme(ws)
    out = os.path.join(post_dir(ws, post_id), "final")
    for f in os.listdir(out) if os.path.isdir(out) else []:     # a re-render replaces the old files so nothing stale is left behind
        if f.startswith("visual"):
            os.remove(os.path.join(out, f))
    carousel = spec.get("type") == "carousel"
    return ve.render_files(spec, out, "visual", "portrait" if carousel else fmt, theme, png, pdf or carousel, tw)


def render_previews(ws, post_id, items, fmt="portrait", png=True):
    theme, tw = ve.load_theme(ws)
    out = os.path.join(post_dir(ws, post_id), "previews")
    if os.path.isdir(out):
        for f in os.listdir(out):
            os.remove(os.path.join(out, f))
    return ve.make_previews(items, out, fmt, theme, png, tw)


# ----------------------------------------------------------- fingerprints

def fingerprints(ws, post_id):
    """Return {idea, visual, content, package} (None where the thing does not exist yet)."""
    pkg = load_package(ws, post_id)
    d = post_dir(ws, post_id)
    out = {"idea": None, "visual": None, "content": None, "package": None}
    idea = pkg.get("idea") or {}
    if idea.get("title"):
        out["idea"] = fp(canon({"title": idea.get("title", ""), "angle": idea.get("angle", "")}))
    spec = load_visual_spec(ws, post_id)
    if spec is not None:
        out["visual"] = ve.spec_hash(spec)
    meta = read_json(os.path.join(d, "final", "visual.meta.json"))
    text = read_text(ws, post_id)
    if text and meta and out["visual"] and meta.get("spec_fingerprint") == out["visual"]:
        svgs = sorted("%s=%s" % (f["file"], f["sha256"]) for f in meta.get("files", []) if f["file"].endswith(".svg") and not f.get("derived"))
        out["content"] = fp("\n".join([text, meta.get("alt_short", ""), meta.get("alt_long", ""), out["visual"]] + svgs))
        body = {k: v for k, v in pkg.items() if k not in VOLATILE}
        out["package"] = fp(canon(body) + out["content"])
    return out


def status(ws, post_id):
    pkg = load_package(ws, post_id)
    d = post_dir(ws, post_id)
    meta = read_json(os.path.join(d, "final", "visual.meta.json")) or {}
    present = {f["file"] for f in meta.get("files", []) if os.path.exists(os.path.join(d, "final", f["file"]))}
    fps = fingerprints(ws, post_id)
    stale = bool(meta) and load_visual_spec(ws, post_id) is not None and meta.get("spec_fingerprint") != fps["visual"]
    missing = []
    if not (pkg.get("idea") or {}).get("title"):
        missing.append("the chosen idea")
    if not read_text(ws, post_id):
        missing.append("the post text")
    if load_visual_spec(ws, post_id) is None:
        missing.append("the picked visual")
    elif not meta or stale:
        missing.append("the rendered visual" + (" (it is out of date: the picked visual changed)" if stale else ""))
    if not pkg.get("suggested_time"):
        missing.append("a suggested time")
    return {"post_id": post_id, "title": pkg.get("title", ""), "fingerprints": fps, "missing": missing,
            "files": {"post_text": bool(read_text(ws, post_id)), "visual_spec": load_visual_spec(ws, post_id) is not None,
                      "final_svg": any(f.endswith(".svg") for f in present), "final_png": any(f.endswith(".png") for f in present),
                      "final_pdf": any(f.endswith(".pdf") for f in present)}}


def list_posts(ws):
    base = os.path.join(ws, "drafts")
    out = []
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        if POST_ID.match(name) and os.path.exists(os.path.join(base, name, "package.json")):
            pkg = read_json(os.path.join(base, name, "package.json"), {})
            out.append({"post_id": name, "title": pkg.get("title", ""), "created": pkg.get("created", "")})
    return out


# -------------------------------------------------------------------- live

def tracker_entry(ws, fields):
    """Add a Post Tracker row through the write guard (the only allowed way to write memory)."""
    lines = ["REGISTER ENTRY", "register: post-tracker"] + ["%s: %s" % (k, v) for k, v in fields.items() if str(v).strip()]
    r = subprocess.run([sys.executable, os.path.join(HERE, "memory_guard.py"), "--workspace", ws, "apply", "--agent", "orchestrator", "--file", "-"],
                       input="\n".join(lines) + "\n", capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def mark_live(ws, post_id, url="", windows=None, live_at=None, reply_windows=None):
    pkg = load_package(ws, post_id)
    windows = windows or pkg.get("measurement_windows") or ["24h", "72h", "7d"]
    added = reminders.add(ws, post_id, windows, live_at)
    if reply_windows:
        added += reminders.add(ws, post_id, reply_windows, live_at, "reply")
    ok, msg = tracker_entry(ws, {"Post ID": post_id, "Date created": pkg.get("created", ""), "Topic": pkg.get("title", ""), "Role": pkg.get("role", ""),
                                 "Status": "live", "Scheduler tool": settings(ws).get("posting_tool", ""), "Post URL": clean_line(url),
                                 "Measurement windows": ", ".join(windows)})
    return {"reminders_added": len(added), "tracker_written": ok, "tracker_message": msg}


# --------------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description="Post files, fingerprints and lifecycle.")
    ap.add_argument("--workspace", default=os.path.dirname(HERE))
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--title", required=True)
    n.add_argument("--role", default="")
    t = sub.add_parser("text")
    t.add_argument("--id", required=True)
    t.add_argument("--file", default="-")
    s = sub.add_parser("set")
    s.add_argument("--id", required=True)
    s.add_argument("--json", default="-")
    v = sub.add_parser("visual-spec")
    v.add_argument("--id", required=True)
    v.add_argument("--file", default="-")
    r = sub.add_parser("render")
    r.add_argument("--id", required=True)
    r.add_argument("--format", choices=["portrait", "square", "carousel"], default="portrait")
    r.add_argument("--no-png", action="store_true")
    r.add_argument("--pdf", action="store_true")
    for name in ("status", "fingerprint"):
        sub.add_parser(name).add_argument("--id", required=True)
    sub.add_parser("list")
    lv = sub.add_parser("live")
    lv.add_argument("--id", required=True)
    lv.add_argument("--url", default="")
    lv.add_argument("--windows")
    lv.add_argument("--reply-windows", help="also remind me to answer comments, for example 1h,6h")
    lv.add_argument("--live-at")
    a = ap.parse_args(argv)
    ws = os.path.abspath(a.workspace)
    read_in = lambda path: sys.stdin.read() if path == "-" else _read(path)
    try:
        if a.cmd == "new":
            print(new_post(ws, a.title, a.role))
        elif a.cmd == "text":
            save_text(ws, a.id, read_in(a.file))
            print("saved post text for %s" % a.id)
        elif a.cmd == "set":
            set_fields(ws, a.id, json.loads(read_in(a.json)))
            print("saved package fields for %s" % a.id)
        elif a.cmd == "visual-spec":
            print("visual fingerprint %s" % save_visual_spec(ws, a.id, json.loads(read_in(a.file))))
        elif a.cmd == "render":
            meta = render_final(ws, a.id, a.format, not a.no_png, a.pdf)
            print("rendered: " + ", ".join(f["file"] for f in meta["files"]))
            for m in meta["messages"]:
                print("note: " + m)
            for w in meta["warnings"]:
                print("warning [%s]: %s" % (w["code"], w["message"]))
        elif a.cmd == "status":
            print(json.dumps(status(ws, a.id), indent=2))
        elif a.cmd == "fingerprint":
            print(json.dumps(fingerprints(ws, a.id), indent=2))
        elif a.cmd == "list":
            for p in list_posts(ws):
                print("%s  %s  %s" % (p["post_id"], p["created"], p["title"]))
        elif a.cmd == "live":
            res = mark_live(ws, a.id, a.url, reminders.parse_windows(a.windows) if a.windows else None, a.live_at,
                            reminders.parse_windows(a.reply_windows, "reply") if a.reply_windows else None)
            print("marked live: %d reminder(s) added; tracker %s" % (res["reminders_added"], "updated" if res["tracker_written"] else "NOT updated: " + res["tracker_message"]))
    except (ValueError, RuntimeError, OSError) as exc:      # PostError, SpecError and bad JSON are all ValueErrors
        print("postkit: %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
