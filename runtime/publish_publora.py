#!/usr/bin/env python3
"""OPTIONAL add-on: send an approved package to Publora (a third-party scheduling service). OFF by default.

    python3 scripts/publish_publora.py status
    python3 scripts/publish_publora.py preview --id P-... --mode draft                        # shows exactly what would be sent; sends nothing
    python3 scripts/publish_publora.py preview --id P-... --mode schedule --at 2026-11-03T08:00:00+05:30
    python3 scripts/publish_publora.py send    --id P-... --mode schedule --at ...            # asks you to type PUBLISH

Turning it on (all three are needed):
  1. In docs/settings.json set  "auto_post": {"provider": "publora", "enabled": true}   (or answer yes in the setup wizard)
  2. Create a Publora account, connect your LinkedIn there, and put your key in the environment variable PUBLORA_API_KEY.
     The key is never written to any file by this software.
  3. Run `preview` first, then `send`.

Safety rules this script keeps, in this order:
  * Off unless you turned it on. No key, no send.
  * The package must be built, and all four of your decisions must still match the exact content (see approvals.py).
  * `preview` is the default; `send` also needs you to type PUBLISH at a keyboard. An AI assistant cannot do that.
  * It only ever creates a Publora DRAFT, or a post SCHEDULED at least 5 minutes ahead (so you can still cancel it in Publora).
    It never posts "right now".
  * The Publora API takes pictures only as public web links, which this software does not have. So by default a package with a
    visual is refused; you can pass --media-url with a public link to the image, or --text-only to send the words alone
    (the image would then have to be added by hand).
  * One send per package fingerprint. If a send ends with an unclear result (for example a timeout), the package is locked
    until you check Publora yourself and run `forget`. Nothing is retried automatically.
  * Every attempt is logged in runs/publish-log.jsonl (no key, no post text).

The first comment and the pinned comment are NOT sent: they need the published post's address, which exists only after it goes live.
Post them by hand from PACKAGE.md.

Honest limits: the request shapes below follow what other open projects document for Publora. This software has been tested only
against a stand-in server, never against the real service. Check Publora's own documentation and pricing first.

Needs Python 3.8+ and nothing else.
"""
import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import package_builder  # noqa: E402
import postkit  # noqa: E402

DEFAULT_BASE = "https://api.publora.com/api/v1"
MIN_AHEAD = datetime.timedelta(minutes=5)
MAX_AHEAD = datetime.timedelta(days=90)
CONFIRM_WORD = "PUBLISH"


class AutopostError(RuntimeError):
    pass


def config(ws):
    cfg = (postkit.settings(ws).get("auto_post") or {})
    return {"enabled": bool(cfg.get("enabled")), "provider": str(cfg.get("provider") or "")}


def base_url():
    url = os.environ.get("PUBLORA_BASE_URL", DEFAULT_BASE).rstrip("/")
    u = urllib.parse.urlparse(url)
    if not (u.scheme == "https" or (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1"))):
        raise AutopostError("PUBLORA_BASE_URL must start with https:// (a local address is allowed for testing)")
    return url


def parse_when(text):
    text = str(text).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.astimezone()


def published_path(ws, post_id):
    return os.path.join(postkit.post_dir(ws, post_id), "published.json")


def log(ws, record):
    os.makedirs(os.path.join(ws, "runs"), exist_ok=True)
    record = dict(record, ts=datetime.datetime.now().astimezone().isoformat(timespec="seconds"))
    with open(os.path.join(ws, "runs", "publish-log.jsonl"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record) + "\n")


def preflight(ws, post_id, mode="draft", at=None, media_url=None, text_only=False, now=None):
    """Everything that must be true before anything is sent. Returns {ok, problems, warnings, payload, summary}. Sends nothing."""
    problems, warnings = [], []
    cfg = config(ws)
    if not cfg["enabled"] or cfg["provider"] != "publora":
        problems.append('Auto-post is off. To turn it on, set "auto_post": {"provider": "publora", "enabled": true} in docs/settings.json.')
    if not os.environ.get("PUBLORA_API_KEY"):
        problems.append("The environment variable PUBLORA_API_KEY is not set. (The key is never stored in a file.)")
    if mode not in ("draft", "schedule"):
        problems.append("mode must be draft or schedule.")
    now = now or datetime.datetime.now().astimezone()
    when = None
    if mode == "schedule":
        try:
            when = parse_when(at)
            if when < now + MIN_AHEAD:
                problems.append("The scheduled time must be at least 5 minutes from now, so you can still cancel it in Publora.")
            elif when > now + MAX_AHEAD:
                problems.append("The scheduled time is more than 90 days away.")
        except (TypeError, ValueError):
            problems.append("Give the time as an ISO date and time with its offset, for example 2026-11-03T08:00:00+05:30.")
    try:
        ok, errors, notes = package_builder.check(ws, post_id)
    except (postkit.PostError, ValueError) as exc:
        return {"ok": False, "problems": problems + [str(exc)], "warnings": warnings, "payload": None, "summary": ""}
    problems += errors
    folder = os.path.join(ws, "exports", "ready-to-paste", post_id)
    fps = postkit.fingerprints(ws, post_id)
    manifest = postkit.read_json(os.path.join(folder, "MANIFEST.json"))
    if ok:
        if not manifest:
            problems.append("Build the ready-to-paste package first (all four decisions must match).")
        elif (manifest.get("fingerprints") or {}).get("package") != fps["package"]:
            problems.append("The package folder is out of date compared with what you approved. Build it again.")
    prior = postkit.read_json(published_path(ws, post_id))
    if prior and prior.get("package_fingerprint") == fps.get("package"):
        problems.append("This exact package was already sent (status: %s). Check Publora before sending again; if you are sure, run `forget` first." % prior.get("status"))
    text = postkit.read_text(ws, post_id).strip()
    if len(text) > package_builder.POST_SOFT_LIMIT:
        warnings.append("The post is %d characters; check Publora's and LinkedIn's limits." % len(text))
    st = postkit.status(ws, post_id)
    has_visual = st["files"]["final_svg"] or st["files"]["final_png"] or st["files"]["final_pdf"]
    if has_visual and not media_url:
        if text_only:
            warnings.append("The post will go out WITHOUT its visual; add the image by hand in Publora or LinkedIn.")
        else:
            problems.append("This package has a visual, but the Publora API takes pictures only as a public web link. Pass --media-url <link to the image>, or --text-only to send the words alone and add the image by hand.")
    if media_url:
        u = urllib.parse.urlparse(media_url)
        if u.scheme != "https":
            problems.append("--media-url must be an https:// link.")
    payload = {"content": text, "platforms": ["<your LinkedIn connection in Publora>"]}
    if when is not None:
        payload["scheduledTime"] = when.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    if media_url:
        payload["mediaUrls"] = [media_url]
    what = "A DRAFT would be created" if mode == "draft" else ("A post would be SCHEDULED for %s" % when.isoformat() if when is not None else "Nothing can be created yet")
    summary = "%s in Publora; %d characters; %s; first and pinned comments are NOT sent." % (what, len(text), "with the image link" if media_url else "text only")
    return {"ok": not problems, "problems": problems, "warnings": warnings + notes, "payload": payload, "summary": summary}


def _request(method, path, key, body=None, timeout=30):
    url = base_url() + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"x-publora-key": key, "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
        return resp.status, (json.loads(raw) if raw.strip() else {})


def _scrub(message, key):
    return str(message).replace(key, "***") if key else str(message)


def resolve_platform(key):
    explicit = os.environ.get("PUBLORA_PLATFORM_ID", "").strip()
    if explicit:
        return explicit
    _status, data = _request("GET", "/platform-connections", key)
    rows = data.get("connections") or data.get("data") or (data if isinstance(data, list) else [])
    ids = [r.get("platformId") for r in rows if isinstance(r, dict) and str(r.get("platformId", "")).startswith("linkedin-")]
    if not ids:
        raise AutopostError("No LinkedIn connection was found in your Publora account. Connect LinkedIn there first (or set PUBLORA_PLATFORM_ID).")
    if len(ids) > 1:
        raise AutopostError("More than one LinkedIn connection was found. Set PUBLORA_PLATFORM_ID to the one you want.")
    return ids[0]


def send(ws, post_id, mode="draft", at=None, media_url=None, text_only=False, confirm="", now=None):
    """Create the Publora draft or scheduled post. Needs the confirm word. Never retries."""
    if confirm != CONFIRM_WORD:
        raise AutopostError("Type %s to confirm. Nothing was sent." % CONFIRM_WORD)
    pre = preflight(ws, post_id, mode, at, media_url, text_only, now)
    fps = postkit.fingerprints(ws, post_id)
    if not pre["ok"]:
        log(ws, {"post_id": post_id, "package_fingerprint": fps.get("package"), "mode": mode, "result": "refused", "problems": len(pre["problems"])})
        raise AutopostError("Not sent:\n  - " + "\n  - ".join(pre["problems"]))
    key = os.environ["PUBLORA_API_KEY"]
    result_path = published_path(ws, post_id)
    base = {"package_fingerprint": fps["package"], "mode": mode, "scheduled_for": pre["payload"].get("scheduledTime", "")}
    try:
        platform = resolve_platform(key)
        payload = dict(pre["payload"], platforms=[platform])
        status, data = _request("POST", "/create-post", key, payload)
    except urllib.error.HTTPError as exc:
        detail = _scrub(exc.read().decode("utf-8", "replace")[:300], key)
        log(ws, dict(base, post_id=post_id, result="failed", http_status=exc.code))
        if exc.code >= 500:                       # the server may have acted before failing: do not allow a blind retry
            postkit.write_json(result_path, dict(base, status="unknown", note="server error %d" % exc.code))
            raise AutopostError("Publora answered with a server error (%d). It is unclear whether anything was created, so this package is locked. Check Publora, then run `forget` if nothing is there. %s" % (exc.code, detail))
        raise AutopostError("Publora refused the request (HTTP %d): %s" % (exc.code, detail))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log(ws, dict(base, post_id=post_id, result="unclear"))
        postkit.write_json(result_path, dict(base, status="unknown", note="no clear answer"))
        raise AutopostError("No clear answer from Publora (%s). It is unclear whether anything was created, so this package is locked. Check Publora, then run `forget` if nothing is there." % _scrub(getattr(exc, "reason", exc), key))
    remote = next((str(data[k]) for k in ("postGroupId", "id", "postId") if isinstance(data, dict) and data.get(k)), "")
    record = dict(base, status="draft" if mode == "draft" else "scheduled", remote_id=remote, http_status=status)
    postkit.write_json(result_path, record)
    log(ws, dict(base, post_id=post_id, result="sent", http_status=status, remote_id=remote))
    pkg = postkit.load_package(ws, post_id)
    postkit.tracker_entry(ws, {"Post ID": post_id, "Date created": pkg.get("created", ""), "Topic": pkg.get("title", ""), "Role": pkg.get("role", ""),
                               "Status": "draft in Publora" if mode == "draft" else "scheduled via Publora", "Scheduler tool": "Publora",
                               "Scheduled for": pre["payload"].get("scheduledTime", ""), "Tool post ID": remote, "Measurement windows": ", ".join(pkg.get("measurement_windows", []))})
    return record


def forget(ws, post_id):
    p = published_path(ws, post_id)
    if os.path.exists(p):
        os.remove(p)
        return True
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="Optional Publora add-on (off by default).")
    ap.add_argument("--workspace", default=os.path.dirname(HERE))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    for name in ("preview", "send"):
        p = sub.add_parser(name)
        p.add_argument("--id", required=True)
        p.add_argument("--mode", choices=["draft", "schedule"], default="draft")
        p.add_argument("--at")
        p.add_argument("--media-url")
        p.add_argument("--text-only", action="store_true")
    f = sub.add_parser("forget")
    f.add_argument("--id", required=True)
    a = ap.parse_args(argv)
    ws = os.path.abspath(a.workspace)
    try:
        if a.cmd == "status":
            c = config(ws)
            print("Auto-post: %s (provider: %s). Key present: %s." % ("ON" if c["enabled"] else "off", c["provider"] or "none", "yes" if os.environ.get("PUBLORA_API_KEY") else "no"))
            return 0
        if a.cmd == "forget":
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                raise AutopostError("`forget` needs a person at a keyboard.")
            if input("Only continue if you checked Publora and nothing was created for %s. Type FORGET: " % a.id).strip() != "FORGET":
                raise AutopostError("Cancelled.")
            print("Cleared." if forget(ws, a.id) else "Nothing to clear.")
            return 0
        pre = preflight(ws, a.id, a.mode, a.at, a.media_url, a.text_only)
        print(pre["summary"])
        for w in pre["warnings"]:
            print("note: " + w)
        for p in pre["problems"]:
            print("BLOCKED: " + p)
        if a.cmd == "preview":
            print(json.dumps(pre["payload"], indent=2))
            print("Nothing was sent." if pre["ok"] else "Fix the points above, then run preview again.")
            return 0 if pre["ok"] else 1
        if not pre["ok"]:
            return 1
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise AutopostError("`send` needs a person at a keyboard to type %s. An AI assistant cannot do this for you." % CONFIRM_WORD)
        typed = input("This will create the Publora %s shown above. Type %s to confirm: " % ("draft" if a.mode == "draft" else "scheduled post", CONFIRM_WORD)).strip()
        rec = send(ws, a.id, a.mode, a.at, a.media_url, a.text_only, typed)
        print("Done: %s (Publora id: %s). Post the first comment by hand from PACKAGE.md." % (rec["status"], rec.get("remote_id") or "not returned"))
        return 0
    except (AutopostError, postkit.PostError) as exc:
        print("publish_publora: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
