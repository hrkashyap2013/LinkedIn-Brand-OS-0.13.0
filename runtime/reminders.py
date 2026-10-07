#!/usr/bin/env python3
"""Results-check reminders for posts that are live.

    python3 scripts/reminders.py add --post-id P-20261006-01 --windows 24h,72h,7d [--live-at 2026-10-06T09:00:00+05:30]
    python3 scripts/reminders.py tick            # fire everything that is due (the scheduler runs this)
    python3 scripts/reminders.py list [--post-id P] [--all]
    python3 scripts/reminders.py due             # what is waiting for you now
    python3 scripts/reminders.py done --post-id P --window 72h      # after you entered the numbers (/metrics)
    python3 scripts/reminders.py cancel --post-id P

Results windows: 24h, 72h, 7d, 15d, 30d, 60d, 90d.
Reply checks (--kind reply): 1h, 3h, 6h, 12h, 24h. "Time to read and answer the comments on your post." You choose the times;
nothing here claims a time is best.

If your computer was off when a reminder came due, it fires at the next tick after the computer is back on
(the scheduler ticks every 30 minutes and, where the system supports it, at start-up). A reminder stays on
your "due" list until you mark it done, so nothing is lost even if you never saw the pop-up.

Reminder messages are generic ("A post is due for its 72h results check"): they carry the post ID but never
the post text. Reminders are stored in runs/reminders.json (private, git-ignored).

Needs Python 3.8+ and nothing else.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOWS = {"24h": 24, "72h": 72, "7d": 168, "15d": 360, "30d": 720, "60d": 1440, "90d": 2160}
REPLY_WINDOWS = {"1h": 1, "3h": 3, "6h": 6, "12h": 12, "24h": 24}
KINDS = ("results", "reply")
LATE_AFTER_HOURS = 2


def parse_time(text):
    text = str(text).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.astimezone()       # a naive time is treated as this computer's local time


def utcnow():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def store_path(ws):
    return os.path.join(ws, "runs", "reminders.json")


class Lock:
    """A tiny cross-platform lock so the scheduler and the app never write at the same moment."""

    def __init__(self, ws):
        os.makedirs(os.path.join(ws, "runs"), exist_ok=True)
        self.path = os.path.join(ws, "runs", ".reminders.lock")

    def __enter__(self):
        deadline = time.time() + 15
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > 60:      # stale lock from a crashed run
                        os.remove(self.path)
                        continue
                except OSError:
                    pass
                if time.time() > deadline:
                    raise RuntimeError("reminders are busy (another run holds the lock); try again in a minute")
                time.sleep(0.1)

    def __exit__(self, *exc):
        try:
            os.remove(self.path)
        except OSError:
            pass


def load(ws):
    try:
        with open(store_path(ws), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) and isinstance(data.get("items"), list) else {"version": 1, "items": []}
    except (OSError, ValueError):
        return {"version": 1, "items": []}


def save(ws, data):
    os.makedirs(os.path.join(ws, "runs"), exist_ok=True)
    tmp = store_path(ws) + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, store_path(ws))


def parse_windows(text, kind="results"):
    table = REPLY_WINDOWS if kind == "reply" else WINDOWS
    out = []
    for w in str(text).replace(";", ",").split(","):
        w = w.strip().lower()
        if not w:
            continue
        if w not in table:
            raise ValueError("unknown window %r. Choose from: %s" % (w, ", ".join(table)))
        if w not in out:
            out.append(w)
    if not out:
        raise ValueError("choose at least one window: %s" % ", ".join(table))
    return out


def kind_of(item):
    return item.get("kind") or "results"


def add(ws, post_id, windows, live_at=None, kind="results"):
    if kind not in KINDS:
        raise ValueError("kind must be results or reply")
    table = REPLY_WINDOWS if kind == "reply" else WINDOWS
    post_id = str(post_id).strip()
    if not post_id or any(ch in post_id for ch in " /\\"):
        raise ValueError("post ID looks wrong: %r" % post_id)
    live = parse_time(live_at) if live_at else utcnow()
    added = []
    with Lock(ws):
        data = load(ws)
        have = {(i["post_id"], i["window"], kind_of(i)) for i in data["items"] if i.get("status") != "cancelled"}
        for w in windows:
            if (post_id, w, kind) in have:
                continue
            item = {"id": "R-%s-%s%s" % (post_id, "reply-" if kind == "reply" else "", w), "post_id": post_id, "window": w, "kind": kind, "live_at": iso(live),
                    "due_at": iso(live + timedelta(hours=table[w])), "status": "pending"}
            data["items"].append(item)
            added.append(item)
        save(ws, data)
    return added


def message_for(item, late_hours):
    if kind_of(item) == "reply":
        msg = "Post %s: time to read and answer the comments. Open your workspace and run /reply." % item["post_id"]
    else:
        msg = "Post %s is due for its %s results check. Open your workspace and run /metrics." % (item["post_id"], item["window"])
    if late_hours > LATE_AFTER_HOURS:
        msg += " It came due earlier, while your computer was off."
    return msg


def tick(ws, now=None, send=True):
    """Fire every pending reminder that is due. Returns the list of items fired."""
    now = now or utcnow()
    fired = []
    with Lock(ws):
        data = load(ws)
        for item in data["items"]:
            if item.get("status") != "pending":
                continue
            due = parse_time(item["due_at"])
            if due > now:
                continue
            late = (now - due).total_seconds() / 3600.0
            delivered = None
            if send:
                try:
                    sys.path.insert(0, HERE)
                    import notify
                    results = notify.notify(ws, "reminder", message=message_for(item, late))
                    delivered = bool(results) and all(ok for _c, ok, _d in results)
                except Exception:                      # a notification problem must never lose a reminder
                    delivered = False
            item.update({"status": "fired", "fired_at": iso(now), "late_hours": round(late, 1), "delivered": delivered})
            fired.append(item)
        if fired:
            save(ws, data)
    return fired


def due(ws, now=None):
    """Reminders waiting for you: pending ones that are due, and fired ones you have not marked done."""
    now = now or utcnow()
    out = []
    for item in load(ws)["items"]:
        if item.get("status") == "fired" or (item.get("status") == "pending" and parse_time(item["due_at"]) <= now):
            out.append(item)
    return sorted(out, key=lambda i: i["due_at"])


def mark(ws, post_id, window, status, kind=None):
    changed = 0
    with Lock(ws):
        data = load(ws)
        for item in data["items"]:
            if (item["post_id"] == post_id and (window is None or item["window"] == window) and (kind is None or kind_of(item) == kind)
                    and item.get("status") in ("pending", "fired")):
                item["status"] = status
                item["closed_at"] = iso(utcnow())
                changed += 1
        if changed:
            save(ws, data)
    return changed


def main(argv=None):
    ap = argparse.ArgumentParser(description="Results-check reminders.")
    ap.add_argument("--workspace", default=os.path.dirname(HERE))
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--post-id", required=True)
    a.add_argument("--windows")
    a.add_argument("--live-at")
    a.add_argument("--kind", choices=KINDS, default="results")
    t = sub.add_parser("tick")
    t.add_argument("--now")
    t.add_argument("--no-notify", action="store_true")
    ls = sub.add_parser("list")
    ls.add_argument("--post-id")
    ls.add_argument("--all", action="store_true")
    sub.add_parser("due")
    d = sub.add_parser("done")
    d.add_argument("--post-id", required=True)
    d.add_argument("--window")
    d.add_argument("--kind", choices=KINDS)
    c = sub.add_parser("cancel")
    c.add_argument("--post-id", required=True)
    args = ap.parse_args(argv)
    ws = os.path.abspath(args.workspace)
    try:
        if args.cmd == "add":
            default = "1h,6h" if args.kind == "reply" else "24h,72h,7d"
            items = add(ws, args.post_id, parse_windows(args.windows or default, args.kind), args.live_at, args.kind)
            print("%d %s reminder(s) added for %s: %s" % (len(items), args.kind, args.post_id, ", ".join("%s (due %s)" % (i["window"], i["due_at"]) for i in items) or "none new"))
        elif args.cmd == "tick":
            fired = tick(ws, parse_time(args.now) if args.now else None, send=not args.no_notify)
            print("reminders: %d fired" % len(fired))
            for i in fired:
                print("  %s %s (delivered: %s)" % (i["post_id"], i["window"], i["delivered"]))
        elif args.cmd == "list":
            for i in load(ws)["items"]:
                if (args.post_id and i["post_id"] != args.post_id) or (not args.all and i.get("status") in ("done", "cancelled")):
                    continue
                print("%s  %-7s %-9s due %s" % (i["id"], kind_of(i), i.get("status"), i["due_at"]))
        elif args.cmd == "due":
            items = due(ws)
            if not items:
                print("No results checks are waiting.")
            for i in items:
                if kind_of(i) == "reply":
                    print("%s reply check (%s) was due %s. Run /reply, then: reminders.py done --post-id %s --window %s --kind reply" % (i["post_id"], i["window"], i["due_at"], i["post_id"], i["window"]))
                else:
                    print("%s %s check was due %s. Run /metrics, then: reminders.py done --post-id %s --window %s" % (i["post_id"], i["window"], i["due_at"], i["post_id"], i["window"]))
        elif args.cmd == "done":
            n = mark(ws, args.post_id, args.window, "done", args.kind)
            print("%d reminder(s) marked done" % n)
            return 0 if n else 1
        elif args.cmd == "cancel":
            print("%d reminder(s) cancelled" % mark(ws, args.post_id, None, "cancelled"))
    except (ValueError, RuntimeError) as exc:
        print("reminders: %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
