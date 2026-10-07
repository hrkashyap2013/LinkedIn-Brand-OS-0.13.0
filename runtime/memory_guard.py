#!/usr/bin/env python3
"""Write guard for the memory registers.

Agents never edit memory files. They return REGISTER ENTRY blocks, and this script applies them:
it checks that the agent may write that register, takes a backup, locks, writes, and verifies.

    python3 scripts/memory_guard.py apply --agent learning --file entries.txt     (or --file - for stdin)
    python3 scripts/memory_guard.py undo [--steps 1]
    python3 scripts/memory_guard.py history [--limit 10]
    python3 scripts/memory_guard.py check
    python3 scripts/memory_guard.py registry
    python3 scripts/memory_guard.py profile-set --section "Voice" --file new.txt --approved-by "Name" --agent listening
    python3 scripts/memory_guard.py export --out my-data.zip
    python3 scripts/memory_guard.py forget --confirm DELETE-MY-DATA [--include-profile-proposals]

An entry looks like this (one block per row; a line "Key: value" per column):

    REGISTER ENTRY
    register: content-memory
    Post ID: P-001
    Date: 2026-10-05
    Topic/Title: Why onboarding fails

Exit codes: 0 ok, 2 bad input, 3 not allowed, 4 verification failed (the write is rolled back), 5 busy.
Needs Python 3.8+ and nothing else.
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
import zipfile
from datetime import datetime, timezone

OK, BAD_INPUT, NOT_ALLOWED, VERIFY_FAILED, BUSY = 0, 2, 3, 4, 5
REGISTERS = ["content-memory", "visual-memory", "experiment-register", "change-register", "learning-register",
             "ideas-and-examples", "experience-bank", "post-tracker", "evidence-library", "approval-log", "profile-proposals"]


def die(code, msg):
    print(f"memory_guard: {msg}", file=sys.stderr)
    sys.exit(code)


class Workspace:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.mem = os.path.join(self.root, "memory")
        self.hist = os.path.join(self.mem, ".history")
        self.lock = os.path.join(self.mem, ".lock")

    def reg_path(self, name):
        return os.path.join(self.mem, name + ".md")

    def registry(self):
        p = os.path.join(self.mem, "registry.json")
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            die(BAD_INPUT, f"missing {p}")
        except ValueError as e:
            die(BAD_INPUT, f"cannot read registry.json: {e}")


# ---------- locking ----------
class Lock:
    def __init__(self, ws, timeout=None, stale=60.0):
        self.ws, self.stale = ws, stale
        self.timeout = float(os.environ.get("MEMORY_GUARD_LOCK_TIMEOUT", "10")) if timeout is None else timeout

    def __enter__(self):
        os.makedirs(self.ws.mem, exist_ok=True)
        end = time.time() + self.timeout
        while True:
            try:
                fd = os.open(self.ws.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.ws.lock) > self.stale:
                        os.remove(self.ws.lock)
                        continue
                except OSError:
                    pass
                if time.time() > end:
                    die(BUSY, "another update is in progress (memory/.lock). Try again in a moment.")
                time.sleep(0.1)

    def __exit__(self, *a):
        try:
            os.remove(self.ws.lock)
        except OSError:
            pass


# ---------- markdown tables ----------
def split_row(line):
    cells = re.split(r"(?<!\\)\|", line.strip())
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [c.strip().replace("\\|", "|") for c in cells]


def is_separator(line):
    t = line.strip()
    return t.startswith("|") and "-" in t and t.replace("|", "").replace(":", "").replace("-", "").replace(" ", "") == ""


def find_table(lines):
    """Return (header_index, last_row_index) of the first markdown table, or None."""
    for i in range(len(lines) - 1):
        if lines[i].lstrip().startswith("|") and is_separator(lines[i + 1]):
            j = i + 1
            while j + 1 < len(lines) and lines[j + 1].lstrip().startswith("|"):
                j += 1
            return i, j
    return None


def clean_value(v):
    return re.sub(r"\s*\n\s*", " ", str(v)).strip().replace("|", "\\|")


# ---------- entry parsing ----------
def parse_entries(text):
    text = re.sub(r"^```[a-z]*\s*$", "", text, flags=re.M)
    blocks = re.split(r"^\s*REGISTER ENTRY\s*$", text, flags=re.M | re.I)[1:]
    if not blocks:
        die(BAD_INPUT, "no 'REGISTER ENTRY' block found")
    entries = []
    for b in blocks:
        reg, fields = None, {}
        for line in b.splitlines():
            if not line.strip() or line.strip().upper() in ("END ENTRY", "END"):
                continue
            if ":" not in line:
                die(BAD_INPUT, f"line without 'Key: value': {line.strip()!r}")
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if k.lower() == "register":
                reg = v.lower()
            else:
                fields[k] = v
        if not reg:
            die(BAD_INPUT, "an entry has no 'register:' line")
        if reg not in REGISTERS:
            die(BAD_INPUT, f"unknown register {reg!r}. Known: {', '.join(REGISTERS)}")
        entries.append((reg, fields))
    return entries


def build_row(header, fields, reg):
    lookup = {h.lower(): h for h in header}
    row = {h: "" for h in header}
    unknown = []
    for k, v in fields.items():
        h = lookup.get(k.lower())
        if h is None:
            unknown.append(k)
        else:
            row[h] = clean_value(v)
    if unknown:
        die(BAD_INPUT, f"unknown column(s) for {reg}: {', '.join(unknown)}. Columns are: {' | '.join(header)}")
    if not any(row.values()):
        die(BAD_INPUT, f"entry for {reg} has no values")
    return "| " + " | ".join(row[h] for h in header) + " |"


# ---------- history ----------
def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def log_event(ws, ev):
    os.makedirs(ws.hist, exist_ok=True)
    with open(os.path.join(ws.hist, "log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(ev) + "\n")


def read_log(ws):
    p = os.path.join(ws.hist, "log.jsonl")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def backup(ws, path, label):
    os.makedirs(ws.hist, exist_ok=True)
    dst = os.path.join(ws.hist, f"{stamp()}__{label}.md")
    shutil.copy2(path, dst)
    return os.path.relpath(dst, ws.root)


# ---------- commands ----------
def cmd_apply(ws, args):
    agent = args.agent.strip().lower()
    reg_cfg = ws.registry().get("registers", {})
    text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
    entries = parse_entries(text)
    for reg, _ in entries:
        if agent not in [a.lower() for a in reg_cfg.get(reg, [])]:
            die(NOT_ALLOWED, f"{agent!r} is not allowed to update {reg}. Allowed: {', '.join(reg_cfg.get(reg, [])) or 'nobody'}")
    with Lock(ws):
        written = 0
        for reg, fields in entries:
            path = ws.reg_path(reg)
            if not os.path.exists(path):
                die(BAD_INPUT, f"missing register file {path}")
            with open(path, encoding="utf-8", newline="") as f:
                raw = f.read()
            nl = "\r\n" if "\r\n" in raw else "\n"
            lines = raw.replace("\r\n", "\n").split("\n")
            tbl = find_table(lines)
            if not tbl:
                die(BAD_INPUT, f"no table found in {reg}.md")
            header = split_row(lines[tbl[0]])
            row = build_row(header, fields, reg)
            existing = [ln.strip() for ln in lines[tbl[0] + 2:tbl[1] + 1]]
            if row.strip() in existing:
                print(f"skipped duplicate row in {reg}")
                continue
            bk = backup(ws, path, reg)
            lines.insert(tbl[1] + 1, row)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                f.write(nl.join(lines))
            os.replace(tmp, path)
            with open(path, encoding="utf-8", newline="") as f:
                after = f.read().replace("\r\n", "\n")
            if row not in after.split("\n"):
                shutil.copy2(os.path.join(ws.root, bk), path)
                die(VERIFY_FAILED, f"could not verify the new row in {reg}; the write was rolled back")
            log_event(ws, {"ts": stamp(), "op": "apply", "agent": agent, "register": reg, "backup": bk})
            written += 1
            print(f"ok {reg}: row added and verified (backup {bk})")
        print(f"{written} row(s) written")


def cmd_undo(ws, args):
    with Lock(ws):
        log = read_log(ws)
        undone = {e["of"] for e in log if e["op"] == "undo"}
        todo = [e for e in log if e["op"] in ("apply", "profile-set") and e["ts"] not in undone][::-1][:args.steps]
        if not todo:
            die(BAD_INPUT, "nothing to undo")
        for e in todo:
            target = ws.reg_path(e["register"]) if e["op"] == "apply" else os.path.join(ws.root, "docs", "brand-profile.md")
            backup(ws, target, "before-undo")
            shutil.copy2(os.path.join(ws.root, e["backup"]), target)
            log_event(ws, {"ts": stamp(), "op": "undo", "of": e["ts"], "register": e["register"]})
            print(f"undone: {e['op']} on {e['register']} ({e['ts']})")


def cmd_history(ws, args):
    for e in read_log(ws)[-args.limit:]:
        print(json.dumps(e))


def cmd_check(ws, args):
    problems = 0
    for reg in REGISTERS:
        p = ws.reg_path(reg)
        if not os.path.exists(p):
            print(f"MISSING  {reg}.md")
            problems += 1
            continue
        lines = open(p, encoding="utf-8").read().split("\n")
        tbl = find_table(lines)
        if not tbl:
            print(f"BROKEN   {reg}.md: no table")
            problems += 1
            continue
        n = len(split_row(lines[tbl[0]]))
        bad = [i + 1 for i in range(tbl[0] + 2, tbl[1] + 1) if len(split_row(lines[i])) != n]
        if bad:
            print(f"BROKEN   {reg}.md: rows with wrong column count at lines {bad}")
            problems += 1
        else:
            print(f"ok       {reg}.md ({tbl[1] - tbl[0] - 1} rows)")
    ws.registry()
    print("registry.json readable")
    sys.exit(1 if problems else 0)


def cmd_registry(ws, args):
    cfg = ws.registry()
    for reg in REGISTERS:
        print(f"{reg:22s} {', '.join(cfg.get('registers', {}).get(reg, []))}")
    print(f"{'brand profile':22s} propose: {', '.join(cfg.get('profile', {}).get('propose', []))}; apply: {', '.join(cfg.get('profile', {}).get('apply', []))} (needs the owner's approval)")


def cmd_profile_set(ws, args):
    agent = args.agent.strip().lower()
    prof = ws.registry().get("profile", {})
    if agent not in [a.lower() for a in prof.get("apply", [])]:
        die(NOT_ALLOWED, f"{agent!r} may not apply profile changes. Allowed: {', '.join(prof.get('apply', []))}")
    if not args.approved_by.strip():
        die(NOT_ALLOWED, "profile changes need --approved-by (the owner's name)")
    path = os.path.join(ws.root, "docs", "brand-profile.md")
    if not os.path.exists(path):
        die(BAD_INPUT, f"missing {path}")
    new_text = (sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()).strip("\n")
    with Lock(ws):
        lines = open(path, encoding="utf-8").read().split("\n")
        want = args.section.strip().lower()
        start = None
        for i, ln in enumerate(lines):
            m = re.match(r"^(#+)\s+(?:\d+\.\s*)?(.*?)\s*$", ln)
            if m and m.group(2).lower() == want:
                start, level = i, len(m.group(1))
                break
        if start is None:
            die(BAD_INPUT, f"section {args.section!r} not found in brand-profile.md")
        end = len(lines)
        for j in range(start + 1, len(lines)):
            m = re.match(r"^(#+)\s", lines[j])
            if m and len(m.group(1)) <= level:
                end = j
                break
        bk = backup(ws, path, "brand-profile")
        lines[start + 1:end] = [""] + new_text.split("\n") + [""]
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(lines))
        if new_text.split("\n")[0] not in open(path, encoding="utf-8").read():
            shutil.copy2(os.path.join(ws.root, bk), path)
            die(VERIFY_FAILED, "could not verify the profile change; rolled back")
        log_event(ws, {"ts": stamp(), "op": "profile-set", "agent": agent, "register": "brand-profile", "section": args.section,
                       "approved_by": args.approved_by, "backup": bk})
        print(f"ok profile section {args.section!r} updated, approved by {args.approved_by} (backup {bk})")


def cmd_export(ws, args):
    out = os.path.abspath(args.out)
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for top in ("memory", "docs", "runs", "drafts", "reports", "inbox"):
            base = os.path.join(ws.root, top)
            for d, dirs, files in os.walk(base):
                dirs[:] = [x for x in dirs if x != ".history"]
                for f in files:
                    if f in (".lock",) or os.path.join(d, f) == out:
                        continue
                    p = os.path.join(d, f)
                    z.write(p, os.path.relpath(p, ws.root))
                    n += 1
    print(f"exported {n} file(s) to {out}")


def cmd_forget(ws, args):
    if args.confirm != "DELETE-MY-DATA":
        die(BAD_INPUT, "this deletes your data. Re-run with --confirm DELETE-MY-DATA to proceed")
    with Lock(ws):
        for reg in REGISTERS:
            if reg == "profile-proposals" and not args.include_profile_proposals:
                continue
            p = ws.reg_path(reg)
            if not os.path.exists(p):
                continue
            lines = open(p, encoding="utf-8").read().split("\n")
            tbl = find_table(lines)
            if tbl:
                del lines[tbl[0] + 2:tbl[1] + 1]
                with open(p, "w", encoding="utf-8", newline="") as f:
                    f.write("\n".join(lines))
        for top in ("runs", "drafts", "reports", "inbox"):
            base = os.path.join(ws.root, top)
            if os.path.isdir(base):
                for name in os.listdir(base):
                    if name.lower() == "readme.md":
                        continue
                    fp = os.path.join(base, name)
                    shutil.rmtree(fp) if os.path.isdir(fp) else os.remove(fp)
        shutil.rmtree(ws.hist, ignore_errors=True)
    print("all register rows, runs, drafts, reports, inbox files and history were deleted. docs/ was left in place.")


def main():
    ap = argparse.ArgumentParser(description="Write guard for the memory registers")
    ap.add_argument("--workspace", default=os.getcwd())
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apply"); a.add_argument("--agent", required=True); a.add_argument("--file", default="-")
    u = sub.add_parser("undo"); u.add_argument("--steps", type=int, default=1)
    h = sub.add_parser("history"); h.add_argument("--limit", type=int, default=10)
    sub.add_parser("check"); sub.add_parser("registry")
    p = sub.add_parser("profile-set"); p.add_argument("--section", required=True); p.add_argument("--file", default="-")
    p.add_argument("--approved-by", required=True); p.add_argument("--agent", default="listening")
    e = sub.add_parser("export"); e.add_argument("--out", required=True)
    f = sub.add_parser("forget"); f.add_argument("--confirm", default=""); f.add_argument("--include-profile-proposals", action="store_true")
    args = ap.parse_args()
    ws = Workspace(args.workspace)
    {"apply": cmd_apply, "undo": cmd_undo, "history": cmd_history, "check": cmd_check, "registry": cmd_registry,
     "profile-set": cmd_profile_set, "export": cmd_export, "forget": cmd_forget}[args.cmd](ws, args)


if __name__ == "__main__":
    main()
