#!/usr/bin/env bash
# LinkedIn Brand Agents - installer (macOS / Linux / WSL / Git Bash)
#
#   bash install.sh --project ~/linkedin     # recommended: a ready-to-use workspace
#   bash install.sh --project ~/linkedin --tool all   # Claude Code AND Codex
#   bash install.sh --global                 # agents + commands for every project
#   bash install.sh --check [--project DIR]  # verify an existing install
#   bash install.sh --dry-run ...            # show what would happen, change nothing
#   bash install.sh --project DIR --wizard   # also run the setup questions (language, days, notifications)
#   bash install.sh --auto                   # unattended: workspace ~/linkedin, Claude Code AND Codex, no questions
#
# Safe to re-run. Agents and commands are updated in place (a timestamped
# .bak copy is kept if you edited them). Your own files (CLAUDE.md, docs/,
# memory/) are NEVER overwritten.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="global"
TARGET=""
DRY=0
CHECK=0
TOOL="claude"
TOOL_SET=0
WIZARD="auto"
AUTO=0

usage() {
  cat <<'EOF'
Usage: bash install.sh [--global | --project DIR] [--tool claude|codex|all] [--check] [--dry-run] [-h]

  --project DIR   Install into DIR/.claude and create DIR/CLAUDE.md,
                  DIR/docs/brand-profile.md and DIR/memory/ (existing files kept).
                  Then run `claude` inside DIR.
  --global        Install agents and commands into ~/.claude (or $CLAUDE_CONFIG_DIR).
                  The agents read docs/ and memory/ from whatever folder you run
                  Claude Code in, so also create a workspace with --project.
  --tool T        Which tool to install for: claude (default), codex, or all.
                  Codex skills always go to $CODEX_HOME/skills (default ~/.codex/skills);
                  in --project mode a Codex workspace also gets an AGENTS.md.
  --check         Verify the install and report problems. Changes nothing.
  --dry-run       Print the actions without doing them.
  --wizard        With --project: run the setup questions after installing (language, posting days and
                  times, image provider, notifications). In a terminal the installer offers this by itself.
  --no-wizard     Never run or offer the setup questions.
  --auto          Unattended install for AI assistants ("install <URL>"): workspace $LBA_WORKSPACE or ~/linkedin, both
                  tools unless --tool is given, no questions, and a short machine-readable result at the end.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --global)  MODE="global" ;;
    --project)
      MODE="project"
      TARGET="${2:-}"
      if [ -z "$TARGET" ]; then echo "error: --project needs a directory" >&2; exit 2; fi
      shift ;;
    --tool)
      TOOL="${2:-}"
      case "$TOOL" in claude|codex|all) ;; *) echo "error: --tool must be claude, codex, or all" >&2; exit 2 ;; esac
      TOOL_SET=1
      shift ;;
    --check)   CHECK=1 ;;
    --dry-run) DRY=1 ;;
    --auto)      AUTO=1 ;;
    --wizard)    WIZARD="yes" ;;
    --no-wizard) WIZARD="no" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ "$AUTO" -eq 1 ]; then
  WIZARD="no"
  if [ "$MODE" != "project" ]; then MODE="project"; TARGET="${LBA_WORKSPACE:-$HOME/linkedin}"; fi
  if [ "$TOOL_SET" -eq 0 ]; then TOOL="all"; fi
fi

# --- sanity: are we running from a full copy of the repo? --------------------
DO_CLAUDE=0; DO_CODEX=0
case "$TOOL" in claude) DO_CLAUDE=1 ;; codex) DO_CODEX=1 ;; all) DO_CLAUDE=1; DO_CODEX=1 ;; esac
if [ "$DO_CLAUDE" -eq 1 ] && { [ ! -d "$SRC/.claude/agents" ] || [ ! -d "$SRC/.claude/commands" ]; }; then
  echo "error: run this script from inside a full clone/unzip of the repo (.claude/ not found next to it)." >&2
  exit 1
fi
if [ "$DO_CODEX" -eq 1 ] && [ ! -d "$SRC/codex/skills" ]; then
  echo "error: codex/skills not found next to this script. Use a full clone/unzip of the repo." >&2
  exit 1
fi
CODEX_DEST="${CODEX_HOME:-$HOME/.codex}/skills"
LEGACY_NAMES="linkedin-content-planner linkedin-idea-lock linkedin-evidence-research linkedin-post-drafter linkedin-humanizer linkedin-visual-producer linkedin-strategy-audit linkedin-publishing-package linkedin-performance-review linkedin-memory-manager linkedin-strategy-review linkedin-governance linkedin-brand-intelligence linkedin-content-intelligence linkedin-anti-repetition linkedin-idea-generation linkedin-idea-selection linkedin-research linkedin-writing linkedin-humanization linkedin-visual-strategy linkedin-visual-production linkedin-visual-qa linkedin-publishing linkedin-measurement linkedin-experiment linkedin-learning linkedin-strategy-learning linkedin-orchestrator"

# --- destinations ------------------------------------------------------------
if [ "$MODE" = "global" ]; then
  DEST_CLAUDE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
  WORKDIR=""
else
  if [ "$DRY" -eq 0 ] && [ "$CHECK" -eq 0 ]; then mkdir -p "$TARGET"; fi
  WORKDIR="$(cd "$TARGET" 2>/dev/null && pwd || echo "$TARGET")"
  DEST_CLAUDE="$WORKDIR/.claude"
fi

INSTALLED=0; UPDATED=0; UNCHANGED=0; KEPT=0; MISSING=0; DIFFERS=0
STAMP="$(date +%Y%m%d%H%M%S)"

say() { printf '%s\n' "$*"; }

do_copy() { # src dst
  if [ "$DRY" -eq 1 ]; then return 0; fi
  mkdir -p "$(dirname "$2")"
  cp "$1" "$2"
}

# Files this project owns: installed, and updated on re-run (with a backup).
managed() { # src dst label
  local src="$1" dst="$2" label="$3"
  if [ "$CHECK" -eq 1 ]; then
    if [ ! -e "$dst" ]; then say "  MISSING   $label"; MISSING=$((MISSING+1))
    elif ! cmp -s "$src" "$dst"; then say "  modified  $label (differs from repo version)"; DIFFERS=$((DIFFERS+1))
    else UNCHANGED=$((UNCHANGED+1)); fi
    return 0
  fi
  if [ ! -e "$dst" ]; then
    say "  install   $label"; do_copy "$src" "$dst"; INSTALLED=$((INSTALLED+1))
  elif cmp -s "$src" "$dst"; then
    UNCHANGED=$((UNCHANGED+1))
  else
    say "  update    $label (backup: $(basename "$dst").bak.$STAMP)"
    if [ "$DRY" -eq 0 ]; then cp "$dst" "$dst.bak.$STAMP"; fi
    do_copy "$src" "$dst"; UPDATED=$((UPDATED+1))
  fi
}

# Files that belong to the user: created once, never overwritten.
userfile() { # src dst label
  local src="$1" dst="$2" label="$3"
  if [ "$CHECK" -eq 1 ]; then
    if [ ! -e "$dst" ]; then say "  MISSING   $label"; MISSING=$((MISSING+1)); fi
    return 0
  fi
  if [ -e "$dst" ]; then
    say "  keep      $label (already exists, not touched)"; KEPT=$((KEPT+1))
  else
    say "  create    $label"; do_copy "$src" "$dst"; INSTALLED=$((INSTALLED+1))
  fi
}

if [ "$CHECK" -eq 1 ]; then say "Checking install"; else say "Installing"; fi
[ "$DRY" -eq 1 ] && say "(dry run - nothing will be changed)"

# Remove agents from earlier versions of this project so nothing is duplicated.
if [ "$CHECK" -eq 0 ]; then
  for n in $LEGACY_NAMES; do
    if [ "$DO_CLAUDE" -eq 1 ] && [ -e "$DEST_CLAUDE/agents/$n.md" ]; then
      say "  remove    legacy agents/$n.md"; if [ "$DRY" -eq 0 ]; then rm -f "$DEST_CLAUDE/agents/$n.md"; fi
    fi
    if [ "$DO_CODEX" -eq 1 ] && [ -d "$CODEX_DEST/$n" ]; then
      say "  remove    legacy skills/$n"; if [ "$DRY" -eq 0 ]; then rm -rf "$CODEX_DEST/$n"; fi
    fi
  done
fi

if [ "$DO_CLAUDE" -eq 1 ]; then
  say "Claude Code -> $DEST_CLAUDE"
  say "Agents:"
  for f in "$SRC"/.claude/agents/*.md; do
    managed "$f" "$DEST_CLAUDE/agents/$(basename "$f")" "agents/$(basename "$f")"
  done
  say "Commands:"
  for f in "$SRC"/.claude/commands/*.md; do
    managed "$f" "$DEST_CLAUDE/commands/$(basename "$f")" "commands/$(basename "$f")"
  done
fi

if [ "$DO_CODEX" -eq 1 ]; then
  say "Codex -> $CODEX_DEST"
  while IFS= read -r f; do
    rel="${f#"$SRC"/codex/skills/}"
    managed "$f" "$CODEX_DEST/$rel" "skills/$rel"
  done < <(find "$SRC/codex/skills" -type f | sort)
fi

if [ "$MODE" = "project" ]; then
  say "Workspace files in $WORKDIR:"
  if [ "$DO_CLAUDE" -eq 1 ]; then userfile "$SRC/CLAUDE.md" "$WORKDIR/CLAUDE.md" "CLAUDE.md"; fi
  if [ "$DO_CODEX" -eq 1 ]; then userfile "$SRC/AGENTS.md" "$WORKDIR/AGENTS.md" "AGENTS.md"; fi
  for f in brand-profile.md schedule.json schedule.example.json settings.json metrics-columns.json; do
    userfile "$SRC/docs/$f" "$WORKDIR/docs/$f" "docs/$f"
  done
  for f in FLOWCHART.md CHANGES-FROM-MASTER.md USER-GUIDE.md TROUBLESHOOTING.md SECURITY-AND-PRIVACY.md VISUALS.md; do
    [ -f "$SRC/docs/$f" ] && managed "$SRC/docs/$f" "$WORKDIR/docs/$f" "docs/$f"
  done
  [ -f "$SRC/VERSION" ] && managed "$SRC/VERSION" "$WORKDIR/VERSION" "VERSION"
  say "Prompts for the apps and for any AI chat:"
  for f in "$SRC"/prompts/*.md; do
    [ -f "$f" ] || continue
    managed "$f" "$WORKDIR/prompts/$(basename "$f")" "prompts/$(basename "$f")"
  done
  for f in "$SRC"/memory/*.md "$SRC"/memory/registry.json; do
    userfile "$f" "$WORKDIR/memory/$(basename "$f")" "memory/$(basename "$f")"
  done
  for d in runs drafts inbox reports; do
    userfile "$SRC/$d/README.md" "$WORKDIR/$d/README.md" "$d/README.md"
  done
  say "Automation scripts:"
  while IFS= read -r f; do
    rel="${f#"$SRC"/runtime/}"
    case "$rel" in *__pycache__*|*.pyc) continue ;; esac
    managed "$f" "$WORKDIR/scripts/$rel" "scripts/$rel"
  done < <(find "$SRC/runtime" -type f | sort)
fi

# --- Claude Code present? ----------------------------------------------------
CLAUDE_OK=1
if [ "$DO_CLAUDE" -eq 1 ] && ! command -v claude >/dev/null 2>&1; then CLAUDE_OK=0; fi
CODEX_OK=1
if [ "$DO_CODEX" -eq 1 ] && ! command -v codex >/dev/null 2>&1; then CODEX_OK=0; fi

say ""
if [ "$CHECK" -eq 1 ]; then
  say "Result: $UNCHANGED ok, $DIFFERS modified, $MISSING missing."
  if [ "$CLAUDE_OK" -eq 0 ]; then say "Warning: the 'claude' command was not found on PATH (Claude Code not installed?)."; fi
  if [ "$CODEX_OK" -eq 0 ]; then say "Warning: the 'codex' command was not found on PATH (Codex not installed?)."; fi
  [ "$MISSING" -eq 0 ] && { say "OK"; exit 0; } || { say "Problems found. Re-run the installer to fix."; exit 1; }
fi

say "Done: $INSTALLED installed, $UPDATED updated, $UNCHANGED unchanged, $KEPT kept."
if [ "$CLAUDE_OK" -eq 0 ]; then say "Note: the 'claude' command was not found on PATH. Install Claude Code first: https://docs.claude.com"; fi
if [ "$CODEX_OK" -eq 0 ]; then say "Note: the 'codex' command was not found on PATH. Install Codex first."; fi

# --- setup questions (language, days and times, notifications) ----------------
if [ "$MODE" = "project" ] && [ "$WIZARD" != "no" ] && [ "$DRY" -eq 0 ]; then
  RUNW=0
  if [ "$WIZARD" = "yes" ]; then
    RUNW=1
  elif [ -t 0 ] && [ -t 1 ] && ! grep -q '"setup_completed": true' "$WORKDIR/docs/settings.json" 2>/dev/null; then
    say ""
    printf 'Answer a few setup questions now (language, posting days and times, notifications)? [Y/n] '
    read -r ANS || ANS="n"
    case "${ANS:-Y}" in n|N|no|NO|No) ;; *) RUNW=1 ;; esac
  fi
  if [ "$RUNW" -eq 1 ]; then
    PY="python3"; command -v python3 >/dev/null 2>&1 || PY="python"
    "$PY" "$WORKDIR/scripts/setup_wizard.py" --workspace "$WORKDIR" || say "Setup was not completed. Run it any time:  python3 scripts/setup_wizard.py"
  fi
fi

say ""
say "Next steps:"
if [ "$MODE" = "project" ]; then
  if grep -q '"setup_completed": true' "$WORKDIR/docs/settings.json" 2>/dev/null; then
    say "  1. Fill in $WORKDIR/docs/brand-profile.md.  (Change your setup any time:  python3 scripts/setup_wizard.py)"
  else
    say "  1. Run the setup questions:  python3 scripts/setup_wizard.py   then fill in $WORKDIR/docs/brand-profile.md"
  fi
  say "  2. cd \"$WORKDIR\""
  STEP3="  3."
  if [ "$DO_CLAUDE" -eq 1 ]; then say "$STEP3 Run: claude    then type /auto  (or /scheduled, or /next one stage at a time)"; STEP3="     or:"; fi
  if [ "$DO_CODEX" -eq 1 ]; then say "$STEP3 codex     then ask: Use \$orchestrator to run my next post"; fi
  say "  4. Optional automatic weekly preparation (after step 1):"
  say "       bash scripts/register-schedule.sh --lead-hours N     (Windows: scripts\\register-schedule.ps1 -LeadHours N)"
else
  say "  1. Create a workspace too:  bash install.sh --project ~/linkedin --tool $TOOL"
  say "  2. Fill in its docs/brand-profile.md and docs/schedule.json, then start your tool inside it."
fi
say "Try it without an AI account:  python3 scripts/demo.py     Start the app:  python3 scripts/chat_app.py"
say "Nothing is ever posted automatically: no agent has a tool that can publish to LinkedIn."
if [ "$AUTO" -eq 1 ]; then
  DOC_STATE="skipped"
  if [ "$DRY" -eq 0 ] && [ -f "$WORKDIR/scripts/doctor.py" ]; then
    say ""
    say "Doctor (checks your setup; it never changes anything):"
    PY="python3"; command -v python3 >/dev/null 2>&1 || PY="python"
    DOC_RC=0
    DOC_OUT="$(PYTHONDONTWRITEBYTECODE=1 "$PY" "$WORKDIR/scripts/doctor.py" --workspace "$WORKDIR" 2>&1)" || DOC_RC=$?
    printf '%s\n' "$DOC_OUT"
    say ""
    say "The install itself succeeded. The doctor lines above check your SETUP, not the install: on a fresh install a blank brand profile, unanswered setup questions, or a missing AI tool or browser are normal. Each line says how to fix it."
    if [ "$DOC_RC" -ne 0 ]; then DOC_STATE="problems"
    elif printf '%s\n' "$DOC_OUT" | grep -q '^WARN'; then DOC_STATE="attention"
    else DOC_STATE="ok"; fi
  fi
  say ""
  say "AUTO-INSTALL-RESULT"
  say "status: ok"
  say "workspace: $WORKDIR"
  say "tools: $TOOL"
  [ "$DO_CODEX" -eq 1 ] && say "codex_skills: $CODEX_DEST"
  say "claude_found: $([ "$CLAUDE_OK" -eq 1 ] && echo yes || echo no)"
  say "codex_found: $([ "$CODEX_OK" -eq 1 ] && echo yes || echo no)"
  say "doctor: $DOC_STATE"
  say "next: ask the owner the setup questions (INSTALL.md step 4), save answers.json, then run: python3 \"$WORKDIR/scripts/setup_wizard.py\" --workspace \"$WORKDIR\" --answers answers.json"
fi
