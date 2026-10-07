#!/usr/bin/env python3
"""Setup wizard for LinkedIn Brand Agents.

    python3 scripts/setup_wizard.py                       # answer the questions
    python3 scripts/setup_wizard.py --show                # print your current settings
    python3 scripts/setup_wizard.py --answers file.json   # no questions: take answers from a file

It asks for: language, who uses the system, which tool prepares your runs, image provider, posting
tool, posting days and times, and how you want to be notified (desktop and/or phone).

It writes:
  docs/settings.json     your choices (no secrets)
  docs/schedule.json     your slots, UTC offset and preparation lead time
  config.local.json      your private phone topic (git-ignored, never shared)

What it will NOT do: ask for a password or API key (set provider keys as environment variables in
your own shell, never in a file here), post anything, or overwrite a file without keeping a .bak copy.
Safe to re-run: your earlier answers are offered as the defaults.

Needs Python 3.8+ and nothing else.
"""
import argparse
import datetime
import json
import os
import re
import secrets
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
IMAGE_PROVIDERS = ["None (I make or upload visuals myself)", "OpenAI", "Google", "Stability AI", "Other"]
POSTING_TOOLS = ["I post manually", "Buffer", "Hootsuite", "Later", "Sprout Social", "Taplio", "Other"]
RUN_TOOLS = ["claude", "codex"]
HUMANIZER_TIERS = ["forensic", "strict", "style"]
DEFAULT_SERVER = "https://ntfy.sh"

SETTINGS_HELP = ("Your setup choices. Change them by re-running `python3 scripts/setup_wizard.py`, or edit by hand. "
                 "Contains no secrets: your private phone topic is in config.local.json. "
                 "Provider API keys are never stored here; set them as environment variables.")

_WORD_FIX = {"mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat", "sun": "Sun"}


class WizardError(ValueError):
    """An answer that is not valid. The message says how to fix it."""


# -------------------------------------------------------------- validation

def norm_day(value):
    key = str(value or "").strip()[:3].lower()
    if key not in _WORD_FIX:
        raise WizardError("'%s' is not a day. Use Mon, Tue, Wed, Thu, Fri, Sat or Sun." % value)
    return _WORD_FIX[key]


def norm_time(value):
    m = re.fullmatch(r"\s*([01]?\d|2[0-3])[:.]([0-5]\d)\s*", str(value or ""))
    if not m:
        raise WizardError("'%s' is not a time. Use 24-hour HH:MM, for example 09:00 or 17:30." % value)
    return "%02d:%s" % (int(m.group(1)), m.group(2))


def norm_offset(value):
    text = str(value or "").strip()
    if text.upper() in ("Z", "UTC", "GMT"):
        return "+00:00"
    m = re.fullmatch(r"([+-])(\d{1,2}):?([0-5]\d)", text)
    if not m or int(m.group(2)) > 14:
        raise WizardError("'%s' is not a UTC offset. Use the form +05:30 or -08:00." % value)
    return "%s%02d:%s" % (m.group(1), int(m.group(2)), m.group(3))


def norm_lead(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        hours = float(value)
    except (TypeError, ValueError):
        raise WizardError("'%s' is not a number of hours." % value)
    if hours < 0 or hours > 168:
        raise WizardError("Lead time must be between 0 and 168 hours.")
    return int(hours) if hours == int(hours) else hours


def norm_slots(slots):
    out, seen = [], set()
    for s in slots or []:
        if not isinstance(s, dict):
            raise WizardError("Each posting slot needs a day and a time.")
        day = norm_day(s.get("day"))
        if day in seen:
            raise WizardError("%s appears twice. Use one slot per day." % day)
        seen.add(day)
        out.append({"day": day, "time": norm_time(s.get("time")), "role": str(s.get("role") or "").strip()})
    out.sort(key=lambda s: DAYS.index(s["day"]))
    return out


def norm_list(value):
    if isinstance(value, str):
        value = re.split(r"[,;\n]", value)
    return [str(v).strip() for v in (value or []) if str(v).strip()]


def norm_choice(value, options, label):
    """Accept a number (1-based), an exact/prefix match of an option, or free text for 'Other'."""
    text = str(value or "").strip()
    if not text:
        raise WizardError("Please choose %s." % label)
    if text.isdigit() and 1 <= int(text) <= len(options):
        return options[int(text) - 1]
    for opt in options:
        if text.lower() == opt.lower() or opt.lower().startswith(text.lower()):
            return opt
    return text


def local_offset():
    z = datetime.datetime.now().astimezone().strftime("%z")  # +0530
    return "%s:%s" % (z[:3], z[3:]) if len(z) == 5 else ""


# ------------------------------------------------------------------ files

def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json(path, data, backup=True, private=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if backup and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                old = fh.read()
        except OSError:
            old = None
        if old is not None and old.strip() and old != text:
            shutil.copyfile(path, "%s.bak.%s" % (path, datetime.datetime.now().strftime("%Y%m%d%H%M%S")))
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    if private and os.name != "nt":
        os.chmod(path, 0o600)


def mask(topic):
    return (topic[:4] + "..." + topic[-3:]) if len(topic) > 8 else ("(set)" if topic else "(none)")


# -------------------------------------------------------------- the model

def apply_answers(ws, a):
    """Validate answers and write the three files. Returns a summary dict. Raises WizardError on bad input."""
    settings_path = os.path.join(ws, "docs", "settings.json")
    schedule_path = os.path.join(ws, "docs", "schedule.json")
    local_path = os.path.join(ws, "config.local.json")
    old = read_json(settings_path)
    old_notes = old.get("notifications") if isinstance(old.get("notifications"), dict) else {}
    sched = read_json(schedule_path)
    local = read_json(local_path)

    language = str(a.get("language") or old.get("language") or "English").strip()
    posting = norm_list(a.get("posting_languages")) or old.get("posting_languages") or [language]
    run_tool = str(a.get("run_tool") or old.get("run_tool") or "claude").strip().lower()
    if run_tool not in RUN_TOOLS:
        raise WizardError("run_tool must be claude or codex.")
    desktop = bool(a.get("desktop", old_notes.get("desktop", False)))
    phone = bool(a.get("phone", old_notes.get("phone", False)))
    server = str(a.get("phone_server") or old_notes.get("phone_server") or DEFAULT_SERVER).strip().rstrip("/")
    if "humanizer_tier" in a and str(a["humanizer_tier"]).strip().lower() not in HUMANIZER_TIERS:
        raise WizardError("humanizer_tier must be forensic, strict or style.")
    if phone and not (server.startswith("https://") or server.startswith("http://127.0.0.1") or server.startswith("http://localhost")):
        raise WizardError("The phone server must start with https://")

    slots = norm_slots(a["slots"]) if "slots" in a else norm_slots(sched.get("slots"))
    offset = norm_offset(a["utc_offset"]) if a.get("utc_offset") else (sched.get("publish_utc_offset") or "")
    lead = norm_lead(a["prep_lead_hours"]) if "prep_lead_hours" in a else sched.get("prep_lead_hours")

    settings = dict(old)
    settings["_help"] = SETTINGS_HELP
    settings.update({
        "setup_completed": True,
        "completed_on": datetime.date.today().isoformat(),
        "language": language,
        "posting_languages": posting,
        "users": norm_list(a["users"]) if "users" in a else old.get("users", []),
        "run_tool": run_tool,
        "image_provider": str(a.get("image_provider") or old.get("image_provider") or IMAGE_PROVIDERS[0]).strip(),
        "posting_tool": str(a.get("posting_tool") or old.get("posting_tool") or POSTING_TOOLS[0]).strip(),
        "notifications": {"desktop": desktop, "phone": phone, "phone_server": server},
        "humanizer_tier": str(a.get("humanizer_tier") or old.get("humanizer_tier") or "strict").strip().lower(),
        "auto_post": {"provider": "publora", "enabled": bool(a["auto_post"]) if "auto_post" in a else bool((old.get("auto_post") or {}).get("enabled"))},
    })
    if settings["humanizer_tier"] not in HUMANIZER_TIERS:
        raise WizardError("humanizer_tier must be forensic, strict or style.")

    sched = dict(sched)
    sched.setdefault("paused", False)
    sched.setdefault("paused_until", None)
    sched["publish_utc_offset"] = offset
    sched["prep_lead_hours"] = lead
    sched["slots"] = slots

    new_topic = False
    if phone and not local.get("ntfy_topic"):
        local["ntfy_topic"] = "lba-" + secrets.token_urlsafe(16)
        new_topic = True
    if server != DEFAULT_SERVER and phone:
        local["ntfy_server"] = server
    else:
        local.pop("ntfy_server", None)

    write_json(settings_path, settings)
    write_json(schedule_path, sched)
    if phone or os.path.exists(local_path):
        write_json(local_path, local, backup=False, private=True)

    return {"settings": settings, "schedule": sched, "topic": local.get("ntfy_topic", ""),
            "new_topic": new_topic, "server": server}


# -------------------------------------------------------------- questions

class Asker:
    def __init__(self, inp=input, out=print):
        self.inp, self.out = inp, out

    def ask(self, prompt, default="", check=None, allow_blank=True):
        suffix = " [%s]" % default if default not in ("", None) else ""
        while True:
            try:
                raw = self.inp("%s%s: " % (prompt, suffix))
            except EOFError:
                raise WizardError("Input ended before the questions were finished. Nothing was changed.")
            raw = raw.strip() or ("" if default is None else str(default))
            if not raw and not allow_blank:
                self.out("  Please enter a value.")
                continue
            if check is None:
                return raw
            try:
                return check(raw)
            except WizardError as exc:
                self.out("  " + str(exc))

    def yes_no(self, prompt, default=False):
        d = "Y/n" if default else "y/N"
        while True:
            try:
                raw = self.inp("%s [%s]: " % (prompt, d)).strip().lower()
            except EOFError:
                raise WizardError("Input ended before the questions were finished. Nothing was changed.")
            if not raw:
                return default
            if raw in ("y", "yes"):
                return True
            if raw in ("n", "no"):
                return False
            self.out("  Please answer y or n.")

    def choose(self, prompt, options, default):
        self.out(prompt)
        for i, opt in enumerate(options, 1):
            self.out("  %d) %s" % (i, opt))
        return self.ask("Choose a number, or type your own", default, lambda v: norm_choice(v, options, "an option"), allow_blank=False)


def interview(ws, ask):
    """Ask every question, offering earlier answers as defaults. Returns an answers dict."""
    old = read_json(os.path.join(ws, "docs", "settings.json"))
    old_notes = old.get("notifications") if isinstance(old.get("notifications"), dict) else {}
    sched = read_json(os.path.join(ws, "docs", "schedule.json"))
    out = ask.out
    a = {}

    out("\nLinkedIn Brand Agents - setup\n" + "-" * 29)
    out("Press Enter to keep the value in [brackets]. Nothing is posted and no passwords or API keys are asked for.\n")

    a["language"] = ask.ask("1. Language the agents talk to you in", old.get("language") or "English", allow_blank=False)
    default_post = ", ".join(old.get("posting_languages") or [a["language"]])
    a["posting_languages"] = ask.ask("   Language(s) your posts are written in (comma separated)", default_post, norm_list)
    a["users"] = ask.ask("2. Who will use this? Names, comma separated (first name is the main owner/approver)",
                         ", ".join(old.get("users") or []), norm_list)
    a["run_tool"] = ask.ask("3. Which tool prepares your scheduled runs (claude or codex)", old.get("run_tool") or "claude",
                            lambda v: norm_choice(v, RUN_TOOLS, "claude or codex"), allow_blank=False)
    a["image_provider"] = ask.choose("4. Image provider (only the name is saved; keep any API key in an environment variable)",
                                     IMAGE_PROVIDERS, old.get("image_provider") or "1")
    a["posting_tool"] = ask.choose("5. Scheduler tool you queue approved posts in", POSTING_TOOLS, old.get("posting_tool") or "1")

    out("\n6. Posting days and times")
    keep = False
    if sched.get("slots"):
        out("   Current slots: " + "; ".join("%s %s%s" % (s.get("day"), s.get("time"), " (%s)" % s["role"] if s.get("role") else "")
                                             for s in sched["slots"]))
        keep = ask.yes_no("   Keep these?", True)
    if not keep:
        slots = []
        while True:
            day = ask.ask("   Day (Mon..Sun)", "", norm_day, allow_blank=False)
            if any(s["day"] == day for s in slots):
                out("   %s is already added. One slot per day." % day)
                continue
            time = ask.ask("   Time to publish (24-hour HH:MM)", "", norm_time, allow_blank=False)
            role = ask.ask("   What is this day for? (optional, for example 'Education'; blank is fine)", "")
            slots.append({"day": day, "time": time, "role": role})
            if not ask.yes_no("   Add another day?", False):
                break
        a["slots"] = slots
    detected = local_offset()
    a["utc_offset"] = ask.ask("   Your UTC offset for these times (detected: %s; change it if your posting clock differs)" % (detected or "unknown"),
                              sched.get("publish_utc_offset") or detected, norm_offset, allow_blank=False)
    lead_default = sched.get("prep_lead_hours")
    out("   Preparation starts this many hours BEFORE each publish time. It is never guessed; leave blank to set it later.")
    a["prep_lead_hours"] = ask.ask("   Lead time in hours", "" if lead_default is None else lead_default, norm_lead)

    out("\n7. Notifications (desktop and phone only)")
    a["desktop"] = ask.yes_no("   Pop-up on this computer when ideas are ready or a run fails?", bool(old_notes.get("desktop")) if old.get("setup_completed") else True)
    a["phone"] = ask.yes_no("   Push message to your phone (free, through the ntfy app)?", bool(old_notes.get("phone", False)))
    if a["phone"]:
        a["phone_server"] = ask.ask("   ntfy server (Enter for the public https://ntfy.sh, or your own https:// address)",
                                    old_notes.get("phone_server") or DEFAULT_SERVER, allow_blank=False)
    out("\n8. Writing and optional add-on")
    a["humanizer_tier"] = ask.ask("   Humanizer strength: forensic (only obvious AI leftovers), strict (also machine patterns, recommended) or style (heaviest)",
                                  old.get("humanizer_tier") or "strict", lambda v: norm_choice(v, HUMANIZER_TIERS, "forensic, strict or style"), allow_blank=False)
    a["auto_post"] = ask.yes_no("   Turn on the OPTIONAL Publora auto-post add-on? (needs your own Publora account and key in PUBLORA_API_KEY; it only creates drafts or scheduled posts after all four of your decisions and a typed confirmation; off is recommended)",
                                bool((old.get("auto_post") or {}).get("enabled")))
    return a


def run_notify_test(ws, out):
    r = subprocess.run([sys.executable, os.path.join(HERE, "notify.py"), "--workspace", ws, "--event", "test"],
                       capture_output=True, text=True)
    for line in (r.stdout + r.stderr).strip().splitlines():
        out("   " + line)
    return r.returncode == 0


def register_runs(ws, settings, sched, out):
    script = "register-schedule.ps1" if os.name == "nt" else "register-schedule.sh"
    path = os.path.join(ws, "scripts", script) if os.path.exists(os.path.join(ws, "scripts", script)) else os.path.join(HERE, script)
    lead = sched.get("prep_lead_hours")
    if lead is None or not sched.get("slots") or not sched.get("publish_utc_offset"):
        out("   Skipped: add at least one day, a UTC offset and a lead time first.")
        return False
    if os.name == "nt":
        argv = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path, "-LeadHours", str(lead), "-Tool", settings["run_tool"]]
    else:
        argv = ["bash", path, "--lead-hours", str(lead), "--tool", settings["run_tool"], "--workspace", ws]
    r = subprocess.run(argv, capture_output=True, text=True)
    for line in (r.stdout + r.stderr).strip().splitlines():
        out("   " + line)
    return r.returncode == 0


def print_summary(res, out):
    s, sc = res["settings"], res["schedule"]
    n = s["notifications"]
    out("\nSaved. Your setup:")
    out("  Language:        %s (posts: %s)" % (s["language"], ", ".join(s["posting_languages"])))
    out("  Users:           %s" % (", ".join(s["users"]) or "(not set)"))
    out("  Prepared by:     %s" % s["run_tool"])
    out("  Image provider:  %s" % s["image_provider"])
    out("  Posting tool:    %s" % s["posting_tool"])
    out("  Slots:           %s" % ("; ".join("%s %s" % (x["day"], x["time"]) for x in sc["slots"]) or "(none yet)"))
    out("  UTC offset:      %s    Lead time: %s" % (sc["publish_utc_offset"] or "(not set)", "not set" if sc["prep_lead_hours"] is None else "%s h" % sc["prep_lead_hours"]))
    out("  Notifications:   desktop %s, phone %s" % ("on" if n["desktop"] else "off", "on" if n["phone"] else "off"))
    out("  Humanizer:       %s    Auto-post add-on: %s" % (s.get("humanizer_tier", "strict"), "ON" if (s.get("auto_post") or {}).get("enabled") else "off"))


def print_phone_help(res, out):
    out("\nPhone setup (one time):")
    out("  1. Install the free 'ntfy' app on your phone (iOS or Android).")
    out("  2. In the app choose 'Subscribe to topic'%s and enter exactly:" % ("" if res["server"] == DEFAULT_SERVER else ", use your own server"))
    out("       %s" % res["topic"])
    out("  Treat that topic like a password: anyone who knows it can read your notifications. They never contain")
    out("  post text, only short messages like 'Your 3 post ideas are ready'. It is stored only in config.local.json.")


def show(ws, out=print):
    s = read_json(os.path.join(ws, "docs", "settings.json"))
    sc = read_json(os.path.join(ws, "docs", "schedule.json"))
    loc = read_json(os.path.join(ws, "config.local.json"))
    if not s.get("setup_completed"):
        out("Setup has not been run yet. Run: python3 scripts/setup_wizard.py")
        return 1
    print_summary({"settings": s, "schedule": {"slots": sc.get("slots", []), "publish_utc_offset": sc.get("publish_utc_offset", ""),
                                               "prep_lead_hours": sc.get("prep_lead_hours")}}, out)
    out("  Phone topic:     %s" % mask(loc.get("ntfy_topic", "")))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="LinkedIn Brand Agents setup wizard.")
    ap.add_argument("--workspace", default=os.path.dirname(HERE), help="your workspace folder (default: the folder above scripts/)")
    ap.add_argument("--answers", help="JSON file of answers; no questions are asked")
    ap.add_argument("--show", action="store_true", help="print the current settings and exit")
    ap.add_argument("--no-test", action="store_true", help="do not send a test notification")
    ap.add_argument("--register", action="store_true", help="with --answers: register the automatic runs afterwards")
    args = ap.parse_args(argv)
    ws = os.path.abspath(args.workspace)
    if args.show:
        return show(ws)
    if not os.path.isdir(os.path.join(ws, "docs")):
        print("error: %s has no docs/ folder. Run the installer first, or pass --workspace." % ws, file=sys.stderr)
        return 2

    ask = Asker()
    try:
        if args.answers:
            answers = read_json(args.answers)
            if not answers:
                raise WizardError("Could not read answers from %s." % args.answers)
            interactive = False
        else:
            if not sys.stdin.isatty():
                raise WizardError("This needs a terminal to ask its questions. Run it yourself, or pass --answers file.json.")
            answers = interview(ws, ask)
            interactive = True
        res = apply_answers(ws, answers)
    except WizardError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled. Nothing was changed.", file=sys.stderr)
        return 130

    print_summary(res, print)
    n = res["settings"]["notifications"]
    try:
        if n["phone"] and res["topic"]:
            print_phone_help(res, print)
        if (n["desktop"] or n["phone"]) and not args.no_test:
            if not interactive or ask.yes_no("\nSend a test notification now?", True):
                if not run_notify_test(ws, print):
                    print("   The test did not reach every channel. Fix the message above, then run:  python3 scripts/notify.py --event test")
        want_register = ask.yes_no("\nRegister the automatic preparation runs now? (needs your computer on at those times)", False) if interactive else args.register
        if want_register:
            register_runs(ws, res["settings"], res["schedule"], print)
    except WizardError as exc:
        print("error: %s" % exc, file=sys.stderr)
    print("\nNext: fill in docs/brand-profile.md, then start your tool in this folder and run /auto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
