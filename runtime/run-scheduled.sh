#!/usr/bin/env bash
# Scheduled preparation runner (macOS / Linux / WSL / Git Bash).
#   bash scripts/run-scheduled.sh --slot Mon [--tool claude|codex] [--force] [--workspace DIR]
# Prepares 3 ideas for a slot and saves them to runs/YYYY-MM-DD-<slot>.md. Never publishes.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="$(dirname "$HERE")"
SLOT=""; TOOL="claude"; FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --slot) SLOT="${2:-}"; shift ;;
    --tool) TOOL="${2:-}"; shift ;;
    --workspace) WS="${2:-}"; shift ;;
    --force) FORCE=1 ;;
    -h|--help) sed -n 2,5p "$0"; exit 0 ;;
    *) echo "error: unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
case "$TOOL" in claude|codex) ;; *) echo "error: --tool must be claude or codex" >&2; exit 2 ;; esac
command -v python3 >/dev/null 2>&1 || { echo "error: python3 is required" >&2; exit 1; }

cd "$WS"
mkdir -p runs
LOG="runs/scheduler.log"
log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }

# Desktop / phone notification (only if you turned one on in the setup wizard). The text is short and
# generic: it never contains idea text. A notification problem can never fail a run.
notify() { # event message
  [ "${LBA_NOTIFY:-1}" = "0" ] && return 0
  [ -f "$HERE/notify.py" ] || return 0
  python3 "$HERE/notify.py" --workspace "$PWD" --event "$1" --message "$2" >> "$LOG" 2>&1 || true
}

[ -n "$SLOT" ] || SLOT="$(date +%a)"
SLOT="$(python3 - "$SLOT" << 'PY'
import sys; print(sys.argv[1].strip()[:3].title())
PY
)"
DATE="$(date +%Y-%m-%d)"
OUT="runs/$DATE-$SLOT.md"

if [ -e "$OUT" ] && [ "$FORCE" -eq 0 ]; then
  log "skip $SLOT $DATE: already prepared ($OUT)"; echo "Already prepared: $OUT (use --force to redo)"; exit 0
fi

# slot details from docs/schedule.json (blank is allowed; nothing is guessed)
INFO="$(python3 - "$SLOT" << 'PY'
import json, sys
slot = sys.argv[1]
try:
    cfg = json.load(open("docs/schedule.json"))
except Exception:
    cfg = {}
role = time = ""; found = False
for s in cfg.get("slots", []):
    if str(s.get("day", ""))[:3].title() == slot:
        role, time, found = s.get("role", ""), s.get("time", ""), True
        off = cfg.get("publish_utc_offset", "")
        if time and off: time = f"{time} (UTC{off})"
        break
print(("1" if found else "0") + "\t" + (role or "(blank)") + "\t" + (time or "(blank)"))
PY
)"
FOUND="${INFO%%$'\t'*}"; REST="${INFO#*$'\t'}"; ROLE="${REST%%$'\t'*}"; TIME="${REST#*$'\t'}"
if [ "$FOUND" != "1" ]; then
  log "no slot named $SLOT in docs/schedule.json; running with blank role"
fi

if [ "$TOOL" = "claude" ]; then
  POINTER="Delegate each step to the matching Claude Code subagent (governance, brand-intelligence, content-intelligence, anti-repetition, idea-generation). The full orchestrator rules are in .claude/commands/scheduled.md if you need them."
  BIN="${CLAUDE_BIN:-claude}"
else
  POINTER="Use the Codex skills (\$governance, \$brand-intelligence, \$content-intelligence, \$anti-repetition, \$idea-generation). The orchestrator rules are in AGENTS.md and \$orchestrator."
  BIN="${CODEX_BIN:-codex}"
fi

PROMPT="$(python3 - "$SLOT" "$DATE" "$TIME" "$ROLE" "$POINTER" << 'PY'
import sys
slot, date, time, role, pointer = sys.argv[1:6]
t = open("scripts/scheduled-prompt.md", encoding="utf-8").read()
for k, v in {"{{SLOT}}": slot, "{{DATE}}": date, "{{TIME}}": time, "{{DAY_ROLE}}": role, "{{POINTER}}": pointer}.items():
    t = t.replace(k, v)
print(t)
PY
)"

if ! command -v "$BIN" >/dev/null 2>&1; then
  MSG="The '$BIN' command was not found on PATH for this scheduled run."
  printf '# Scheduled preparation FAILED: %s %s\n\n%s\n' "$SLOT" "$DATE" "$MSG" > "runs/$DATE-$SLOT.FAILED.md"
  log "FAILED $SLOT $DATE: $MSG"; notify failed "Preparation for $SLOT did not run: the $BIN command was not found."; echo "$MSG" >&2; exit 1
fi

log "start $SLOT $DATE via $TOOL"
TMP="$(mktemp)"
EXTRA=()
if [ "$TOOL" = "claude" ] && [ -n "${CLAUDE_EXTRA_ARGS:-}" ]; then read -r -a EXTRA <<< "$CLAUDE_EXTRA_ARGS"; fi
set +e
if [ "$TOOL" = "claude" ]; then "$BIN" -p "$PROMPT" ${EXTRA[@]+"${EXTRA[@]}"} > "$TMP" 2>> "$LOG"; else "$BIN" exec "$PROMPT" > "$TMP" 2>> "$LOG"; fi
RC=$?
set -e

if [ "$RC" -ne 0 ] || [ ! -s "$TMP" ]; then
  printf '# Scheduled preparation FAILED: %s %s\n\nThe tool exited with code %s or returned no output. See runs/scheduler.log.\n' "$SLOT" "$DATE" "$RC" > "runs/$DATE-$SLOT.FAILED.md"
  log "FAILED $SLOT $DATE rc=$RC"; rm -f "$TMP"; notify failed "Preparation for $SLOT failed. Open the runs folder to see why."; exit 1
fi

{
  printf '# Scheduled preparation: %s %s\n\n' "$SLOT" "$DATE"
  printf 'Status: PREPARED. Waiting for you to select 1 idea. Nothing has been drafted, approved, or published.\n\n---\n\n'
  cat "$TMP"
} > "$OUT"
rm -f "$TMP"
log "done $SLOT $DATE -> $OUT"
notify prepared "Your 3 post ideas for $SLOT are ready. Open your workspace and pick one."
echo "Prepared: $OUT"
