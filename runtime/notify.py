#!/usr/bin/env python3
"""Desktop and phone notifications for LinkedIn Brand Agents.

    python3 scripts/notify.py --event prepared
    python3 scripts/notify.py --event failed --message "Preparation failed for Mon"
    python3 scripts/notify.py --event test            # used by the setup wizard
    python3 scripts/notify.py --event test --dry-run  # show what would be sent

Channels (turn them on with `python3 scripts/setup_wizard.py`):
  desktop  a native pop-up: macOS (osascript), Linux (notify-send), Windows / WSL (PowerShell).
  phone    a push message through ntfy (https://ntfy.sh, or your own ntfy server). You install the
           free ntfy app on your phone and subscribe to your private topic.

Rules this script keeps:
  * Notifications are SHORT and GENERIC. They never contain idea text, drafts, brand details or
    metrics, because a phone topic is shared-secret, not end-to-end encrypted.
  * Nothing here posts to LinkedIn. It only tells you that something is waiting for you.
  * For every event except `test`, a delivery problem is reported on screen and the exit code is
    still 0, so a notification can never break a scheduled run.
  * The phone topic lives in config.local.json (git-ignored), never in docs/settings.json.

Needs Python 3.8+ and nothing else.
"""
import argparse
import base64
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_SERVER = "https://ntfy.sh"
APP_NAME = "LinkedIn Brand Agents"

EVENTS = {
    "prepared": ("Ideas are ready", "Your 3 post ideas are ready. Open your workspace and pick one."),
    "failed": ("Preparation failed", "A scheduled preparation did not finish. Open the runs folder to see why."),
    "reminder": ("Results check due", "A post is due for a results check. Open your workspace and run /metrics."),
    "test": ("Notifications work", "This is a test from LinkedIn Brand Agents. You can ignore it."),
}
PRIORITY = {"prepared": 3, "failed": 4, "reminder": 3, "test": 2}
TAGS = {"prepared": ["memo"], "failed": ["warning"], "reminder": ["bell"], "test": ["white_check_mark"]}

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean(text, limit):
    """Strip control characters and cap the length. Notification text is never trusted."""
    text = _CONTROL.sub(" ", str(text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_config(workspace):
    settings = load_json(os.path.join(workspace, "docs", "settings.json"))
    local = load_json(os.path.join(workspace, "config.local.json"))
    notes = settings.get("notifications") if isinstance(settings.get("notifications"), dict) else {}
    server = str(local.get("ntfy_server") or notes.get("phone_server") or DEFAULT_SERVER).strip()
    return {
        "desktop": bool(notes.get("desktop")),
        "phone": bool(notes.get("phone")),
        "server": server,
        "topic": str(local.get("ntfy_topic") or "").strip(),
    }


# ---------------------------------------------------------------- desktop

def _is_wsl():
    return "microsoft" in platform.release().lower()


def _powershell_script(title, message):
    enc = lambda s: base64.b64encode(s.encode("utf-8")).decode("ascii")
    return (
        "$t=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s'));"
        "$m=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s'));"
        "try{"
        "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null;"
        "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        "$n=$x.GetElementsByTagName('text');"
        "$n.Item(0).AppendChild($x.CreateTextNode($t))|Out-Null;"
        "$n.Item(1).AppendChild($x.CreateTextNode($m))|Out-Null;"
        "$id='{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe';"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($id).Show([Windows.UI.Notifications.ToastNotification]::new($x))"
        "}catch{"
        "Add-Type -AssemblyName System.Windows.Forms;Add-Type -AssemblyName System.Drawing;"
        "$i=New-Object System.Windows.Forms.NotifyIcon;$i.Icon=[System.Drawing.SystemIcons]::Information;$i.Visible=$true;"
        "$i.ShowBalloonTip(5000,$t,$m,[System.Windows.Forms.ToolTipIcon]::Info);Start-Sleep -Seconds 6;$i.Dispose()}"
    ) % (enc(title), enc(message))


def desktop_command(title, message):
    """Return (argv, None) for this machine, or (None, reason). Arguments are passed as a list, never through a shell."""
    system = platform.system()
    if system == "Darwin":
        if not shutil.which("osascript"):
            return None, "osascript not found"
        return ["osascript", "-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
                "-e", "end run", title, message], None
    if system == "Windows" or _is_wsl():
        exe = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")
        if not exe:
            return None, "PowerShell not found"
        return [exe, "-NoProfile", "-NonInteractive", "-Command", _powershell_script(title, message)], None
    if shutil.which("notify-send"):
        return ["notify-send", "--app-name", APP_NAME, title, message], None
    return None, "notify-send not found (on Debian/Ubuntu: sudo apt install libnotify-bin)"


def send_desktop(title, message, dry_run=False):
    argv, why = desktop_command(title, message)
    if argv is None:
        return False, why
    if dry_run:
        return True, "would show a desktop notification (%s)" % os.path.basename(argv[0])
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "exit code %s" % r.returncode).strip()[:200]
    return True, "shown"


# ------------------------------------------------------------------ phone

def valid_server(server):
    """https only, except a loopback address (used by the tests and by self-hosted setups on the same machine)."""
    u = urllib.parse.urlparse(server)
    if not u.hostname:
        return False
    return u.scheme == "https" or (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1"))


def send_phone(server, topic, title, message, event, dry_run=False):
    if not topic:
        return False, "no phone topic yet (run the setup wizard)"
    if not valid_server(server):
        return False, "server must start with https:// (got %r)" % server
    payload = {"topic": topic, "title": title, "message": message,
               "priority": PRIORITY.get(event, 3), "tags": TAGS.get(event, [])}
    if dry_run:
        return True, "would send a push message to %s (topic hidden)" % server
    req = urllib.request.Request(server.rstrip("/"), data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if 200 <= resp.status < 300:
                return True, "sent"
            return False, "server answered %s" % resp.status
    except urllib.error.HTTPError as exc:
        return False, "server answered %s" % exc.code
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return False, str(getattr(exc, "reason", exc))[:200]


# ------------------------------------------------------------------- main

def notify(workspace, event, title=None, message=None, dry_run=False):
    """Send on every enabled channel. Returns a list of (channel, ok, detail)."""
    cfg = load_config(workspace)
    default_title, default_msg = EVENTS[event]
    title = clean(title or default_title, 80)
    message = clean(message or default_msg, 300)
    results = []
    if cfg["desktop"]:
        results.append(("desktop",) + send_desktop(title, message, dry_run))
    if cfg["phone"]:
        results.append(("phone",) + send_phone(cfg["server"], cfg["topic"], title, message, event, dry_run))
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description="Send a desktop and/or phone notification.")
    ap.add_argument("--event", choices=sorted(EVENTS), default="test")
    ap.add_argument("--title")
    ap.add_argument("--message")
    ap.add_argument("--workspace", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--dry-run", action="store_true", help="show what would be sent, send nothing")
    args = ap.parse_args(argv)

    results = notify(args.workspace, args.event, args.title, args.message, args.dry_run)
    if not results:
        print("notifications: no channel is turned on (run: python3 scripts/setup_wizard.py)")
        return 1 if args.event == "test" else 0
    failed = False
    for channel, ok, detail in results:
        print("notifications: %s: %s%s" % (channel, "ok" if ok else "FAILED", " - " + detail if detail else ""))
        failed = failed or not ok
    return 1 if (failed and args.event == "test") else 0


if __name__ == "__main__":
    sys.exit(main())
