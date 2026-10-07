#!/usr/bin/env python3
"""Checks that your setup is healthy and tells you how to fix anything that is not.

    python3 scripts/doctor.py                 # checks only; changes nothing, makes no AI call
    python3 scripts/doctor.py --json
    python3 scripts/doctor.py --test-ai       # also sends one tiny request to your AI tool (it uses a little of your plan)

Status words: OK (fine), WARN (works, but something is off or missing), FAIL (something is broken), INFO (for your information).
The exit code is 1 if any check FAILs, so you can use it in a script.

Needs Python 3.8+ and nothing else.
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def item(status, title, detail="", fix=""):
    return {"status": status, "title": title, "detail": detail, "fix": fix}


def tool_version(exe):
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15)
        return (r.stdout or r.stderr).strip().splitlines()[0][:80] if (r.stdout or r.stderr).strip() else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def run_checks(ws, test_ai=False):
    out = []
    ver = os.path.join(ws, "VERSION")
    version = "unknown"
    if os.path.exists(ver):
        with open(ver, encoding="utf-8") as fh:
            version = fh.read().strip()
    out.append(item("INFO", "Version", "LinkedIn Brand Agents %s on %s, Python %s" % (version, platform.system(), platform.python_version())))
    if sys.version_info < (3, 8):
        out.append(item("FAIL", "Python version", "Python %s is too old." % platform.python_version(), "Install Python 3.8 or newer."))

    missing = [d for d in ("docs", "memory", "scripts") if not os.path.isdir(os.path.join(ws, d))]
    if missing:
        out.append(item("FAIL", "Workspace folders", "Missing: %s" % ", ".join(missing), "Run the installer again (bash install.sh --project <folder>)."))
        return out
    out.append(item("OK", "Workspace folders", "docs, memory and scripts are present."))
    if not os.path.isdir(os.path.join(ws, "prompts")):
        out.append(item("WARN", "Prompts folder", "prompts/ is missing, so the apps cannot load the agents' rules.", "Run the installer again."))

    s = read_json(os.path.join(ws, "docs", "settings.json")) or {}
    if not s.get("setup_completed"):
        out.append(item("WARN", "Setup questions", "Not answered yet.", "Run: python3 scripts/setup_wizard.py"))
    else:
        out.append(item("OK", "Setup questions", "Language %s, tool %s, humanizer %s." % (s.get("language") or "?", s.get("run_tool") or "?", s.get("humanizer_tier") or "strict")))

    prof = os.path.join(ws, "docs", "brand-profile.md")
    if os.path.exists(prof):
        with open(prof, encoding="utf-8") as fh:
            text = fh.read()
        blank = sum(1 for ln in text.splitlines() if ln.strip().startswith("- ") and ln.rstrip().endswith(":"))
        filled = sum(1 for ln in text.splitlines() if ln.strip().startswith("- ") and ":" in ln and not ln.rstrip().endswith(":"))
        if filled < 5:
            out.append(item("WARN", "Brand profile", "Only %d field(s) filled in (%d blank)." % (filled, blank), "Fill in docs/brand-profile.md; the agents never guess blank fields."))
        else:
            out.append(item("OK", "Brand profile", "%d fields filled in, %d still blank." % (filled, blank)))
    else:
        out.append(item("FAIL", "Brand profile", "docs/brand-profile.md is missing.", "Run the installer again."))

    tool = (s.get("run_tool") or "claude").lower()
    exe = shutil.which(os.environ.get("CODEX_BIN", "codex") if tool == "codex" else os.environ.get("CLAUDE_BIN", "claude"))
    if exe:
        out.append(item("OK", "AI tool (%s)" % tool, "%s %s" % (exe, tool_version(exe))))
    elif os.environ.get("LBA_AI_CMD"):
        out.append(item("INFO", "AI tool", "A custom command is set in LBA_AI_CMD (used by the demo and tests)."))
    else:
        out.append(item("FAIL", "AI tool (%s)" % tool, "The '%s' command was not found on PATH." % tool, "Install and sign in to %s, or try: python3 scripts/demo.py" % ("Codex" if tool == "codex" else "Claude Code")))
    if test_ai:
        try:
            import chat_core
            reply = chat_core.run_ai(ws, "LBA-STAGE: chat\nReply with the single word OK.\n## Owner's message\nTest", timeout=180)
            out.append(item("OK", "AI test request", "Your tool answered: %s" % reply[:60]))
        except Exception as exc:                                    # the point is to show the reason
            out.append(item("FAIL", "AI test request", str(exc)[:300], "Run the tool by hand in a terminal once and fix what it says (sign in, plan, permissions)."))

    try:
        import visual_engine
        b = visual_engine.find_browser()
    except Exception:
        b = None
    out.append(item("OK", "Browser for PNG and PDF", b) if b else item("WARN", "Browser for PNG and PDF", "No Chrome or Edge found; visuals will be SVG only.", "Install Chrome or Edge, or set LBA_BROWSER to its full path."))

    notes = s.get("notifications") or {}
    local = read_json(os.path.join(ws, "config.local.json")) or {}
    if not (notes.get("desktop") or notes.get("phone")):
        out.append(item("INFO", "Notifications", "None turned on."))
    else:
        if notes.get("desktop"):
            need = {"Darwin": "osascript", "Windows": "powershell"}.get(platform.system(), "notify-send")
            out.append(item("OK", "Desktop pop-ups", "%s found." % need) if shutil.which(need) or shutil.which(need + ".exe") else
                       item("WARN", "Desktop pop-ups", "'%s' was not found." % need, "On Debian or Ubuntu: sudo apt install libnotify-bin"))
        if notes.get("phone"):
            out.append(item("OK", "Phone push", "A private topic is set.") if local.get("ntfy_topic") else
                       item("WARN", "Phone push", "Turned on but no topic exists.", "Run: python3 scripts/setup_wizard.py"))
    cfg = os.path.join(ws, "config.local.json")
    if os.path.exists(cfg) and os.name != "nt" and (os.stat(cfg).st_mode & 0o077):
        out.append(item("WARN", "Private file permissions", "config.local.json can be read by other users.", "Run: chmod 600 config.local.json"))

    sched = read_json(os.path.join(ws, "docs", "schedule.json")) or {}
    if shutil.which("crontab") and platform.system() != "Windows":
        try:
            cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10).stdout
            registered = "linkedin-brand-agents" in cron and ws in cron
        except (OSError, subprocess.SubprocessError):
            registered = None
        if registered is None:
            out.append(item("INFO", "Scheduler", "Could not read your crontab."))
        elif registered:
            out.append(item("OK", "Scheduler", "Preparation runs and the reminder check are registered."))
        elif sched.get("slots"):
            out.append(item("WARN", "Scheduler", "You have posting slots but nothing is registered, so no automatic runs or reminder checks happen.", "Run: bash scripts/register-schedule.sh --lead-hours <hours>"))
        else:
            out.append(item("INFO", "Scheduler", "Not registered (no posting slots set)."))
    elif platform.system() == "Windows" and shutil.which("schtasks"):
        r = subprocess.run(["schtasks", "/query", "/tn", "LinkedInBrand-Reminders"], capture_output=True, text=True)
        out.append(item("OK", "Scheduler", "The reminder task is registered.") if r.returncode == 0 else
                   item("WARN", "Scheduler", "The reminder task is not registered.", "Run: powershell -ExecutionPolicy Bypass -File scripts\\register-schedule.ps1 -RemindersOnly"))
    else:
        out.append(item("INFO", "Scheduler", "Could not check on this system."))

    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "memory_guard.py"), "--workspace", ws, "check"], capture_output=True, text=True, timeout=60)
        out.append(item("OK", "Memory registers", "All registers are healthy.") if r.returncode == 0 else
                   item("FAIL", "Memory registers", (r.stdout + r.stderr).strip()[:300], "Restore with: python3 scripts/memory_guard.py undo"))
    except (OSError, subprocess.SubprocessError) as exc:
        out.append(item("WARN", "Memory registers", "Could not run the check: %s" % exc))

    try:
        import reminders
        due = reminders.due(ws)
        out.append(item("INFO", "Reminders", "%d waiting for you." % len(due)) if due else item("OK", "Reminders", "Nothing is waiting."))
    except Exception as exc:
        out.append(item("WARN", "Reminders", str(exc)[:200]))

    auto = s.get("auto_post") or {}
    if auto.get("enabled"):
        out.append(item("OK", "Auto-post add-on", "ON (Publora), key present.") if os.environ.get("PUBLORA_API_KEY") else
                   item("WARN", "Auto-post add-on", "Turned on but PUBLORA_API_KEY is not set in this shell.", "Set the variable, or turn it off in docs/settings.json."))
    else:
        out.append(item("INFO", "Auto-post add-on", "Off (the default)."))

    try:
        os.makedirs(os.path.join(ws, "runs"), exist_ok=True)
        probe = os.path.join(ws, "runs", ".doctor-probe")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        out.append(item("OK", "Writing files", "The runs folder is writable."))
    except OSError as exc:
        out.append(item("FAIL", "Writing files", str(exc), "Check the folder's permissions."))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check that the setup is healthy.")
    ap.add_argument("--workspace", default=os.path.dirname(HERE))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--test-ai", action="store_true", help="also send one tiny request to your AI tool")
    a = ap.parse_args(argv)
    res = run_checks(os.path.abspath(a.workspace), a.test_ai)
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        for r in res:
            print("%-5s %s%s" % (r["status"], r["title"], (": " + r["detail"]) if r["detail"] else ""))
            if r["fix"] and r["status"] in ("WARN", "FAIL"):
                print("      fix: %s" % r["fix"])
        counts = {k: sum(1 for r in res if r["status"] == k) for k in ("OK", "WARN", "FAIL")}
        print("\n%d OK, %d to look at, %d broken." % (counts["OK"], counts["WARN"], counts["FAIL"]))
    return 1 if any(r["status"] == "FAIL" for r in res) else 0


if __name__ == "__main__":
    sys.exit(main())
