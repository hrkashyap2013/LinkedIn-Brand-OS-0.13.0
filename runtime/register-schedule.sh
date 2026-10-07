#!/usr/bin/env bash
# Register (or remove) the scheduled runs in cron (macOS / Linux / WSL).
#   bash scripts/register-schedule.sh --lead-hours 12 [--tool claude|codex] [--dry-run]
#   bash scripts/register-schedule.sh --reminders-only      # only the results-check reminders (no preparation runs)
#   bash scripts/register-schedule.sh --no-reminders        # only the preparation runs
#   bash scripts/register-schedule.sh --remove
# Reads docs/schedule.json. Each slot's preparation starts LEAD hours before its publish
# time. The lead time is never guessed: set it with --lead-hours or "prep_lead_hours" in the file.
# It also registers the reminder check (every 30 minutes, and at start-up where the system supports it), so a
# results-check reminder that came due while your computer was off still reaches you once it is back on.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="$(dirname "$HERE")"
TOOL="claude"; LEAD=""; DRY=0; REMOVE=0; REM="both"
CRONTAB="${CRONTAB_CMD:-crontab}"
BEGIN="# BEGIN linkedin-brand-agents"; END="# END linkedin-brand-agents"

while [ $# -gt 0 ]; do
  case "$1" in
    --tool) TOOL="${2:-}"; shift ;;
    --lead-hours) LEAD="${2:-}"; shift ;;
    --workspace) WS="${2:-}"; shift ;;
    --dry-run) DRY=1 ;;
    --remove) REMOVE=1 ;;
    --reminders-only) REM="only" ;;
    --no-reminders) REM="none" ;;
    -h|--help) sed -n 2,9p "$0"; exit 0 ;;
    *) echo "error: unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
case "$TOOL" in claude|codex) ;; *) echo "error: --tool must be claude or codex" >&2; exit 2 ;; esac

existing() { "$CRONTAB" -l 2>/dev/null || true; }
strip_block() { awk -v b="$BEGIN" -v e="$END" '$0==b{skip=1;next} $0==e{skip=0;next} !skip' ; }

if [ "$REMOVE" -eq 1 ]; then
  if [ "$DRY" -eq 1 ]; then echo "(dry run) would remove the linkedin-brand-agents block from crontab"; exit 0; fi
  KEEP="$(existing | strip_block)"
  if [ -n "$KEEP" ]; then printf '%s\n' "$KEEP" | "$CRONTAB" -; else printf '' | "$CRONTAB" -; fi
  echo "Removed scheduled runs and reminder checks."; exit 0
fi

command -v python3 >/dev/null 2>&1 || { echo "error: python3 is required" >&2; exit 1; }

LINES="$(python3 - "$WS" "$TOOL" "$LEAD" "$REM" << 'PY'
import json, platform, sys
from datetime import datetime, timedelta, timezone
ws, tool, lead_arg, rem = sys.argv[1:5]
out = []
if rem != "none":
    py = sys.executable or "python3"
    out.append(f'*/30 * * * * cd "{ws}" && "{py}" scripts/reminders.py tick >> runs/scheduler.log 2>&1')
    if platform.system() != "Darwin":      # macOS cron has no @reboot; the 30-minute tick catches up after start-up there
        out.append(f'@reboot sleep 90 && cd "{ws}" && "{py}" scripts/reminders.py tick >> runs/scheduler.log 2>&1')
if rem != "only":
    with open(f"{ws}/docs/schedule.json", encoding="utf-8") as fh:
        cfg = json.load(fh)
    off = cfg.get("publish_utc_offset") or ""
    lead = lead_arg if lead_arg != "" else cfg.get("prep_lead_hours")
    slots = cfg.get("slots") or []
    if not slots: sys.exit("error: docs/schedule.json has no slots. Add your publishing days first.")
    if not off: sys.exit('error: set "publish_utc_offset" (for example "+05:30") in docs/schedule.json.')
    if lead in (None, ""): sys.exit('error: the preparation lead time is not set. Pass --lead-hours N or set "prep_lead_hours" in docs/schedule.json. It is not guessed.')
    lead = float(lead)
    sign = -1 if off.startswith("-") else 1
    hh, mm = off.lstrip("+-").split(":")
    tz = timezone(sign * timedelta(hours=int(hh), minutes=int(mm)))
    days = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    now = datetime.now(tz)
    runs = []
    for s in slots:
        d = str(s.get("day",""))[:3].title()
        if d not in days: sys.exit(f"error: unknown day in slot: {s!r}")
        th, tm = (s.get("time") or "").split(":")
        delta = (days.index(d) - now.weekday()) % 7
        base = (now + timedelta(days=delta)).replace(hour=int(th), minute=int(tm), second=0, microsecond=0)
        local = (base - timedelta(hours=lead)).astimezone()
        dow = (local.weekday() + 1) % 7
        cmd = f'cd "{ws}" && bash scripts/run-scheduled.sh --slot {d} --tool {tool} >> runs/scheduler.log 2>&1'
        runs.append(f"{local.minute} {local.hour} * * {dow} {cmd}")
    out = runs + out
print("\n".join(out))
PY
)"

BLOCK="$BEGIN"$'\n'"$LINES"$'\n'"$END"
echo "Scheduled entries (computed in this machine's local time):"
echo "$BLOCK"
if [ "$DRY" -eq 1 ]; then echo "(dry run - crontab not changed)"; exit 0; fi
KEEP="$(existing | strip_block)"
if [ -n "$KEEP" ]; then printf '%s\n%s\n' "$KEEP" "$BLOCK" | "$CRONTAB" -; else printf '%s\n' "$BLOCK" | "$CRONTAB" -; fi
echo "Registered. If your clock changes for daylight saving, run this again."
