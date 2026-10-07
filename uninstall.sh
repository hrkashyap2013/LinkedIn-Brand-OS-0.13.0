#!/usr/bin/env bash
# LinkedIn Brand Agents - uninstaller
#
#   bash uninstall.sh --global
#   bash uninstall.sh --project ~/linkedin
#   bash uninstall.sh --global --tool codex     # (claude | codex | all; default claude)
#   bash uninstall.sh --dry-run --global
#
# Removes ONLY the agent and command files that this repo ships.
# Your CLAUDE.md, docs/ and memory/ (your brand profile and post history)
# are never deleted.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE=""
TARGET=""
DRY=0
TOOL="claude"
LEGACY_NAMES="linkedin-content-planner linkedin-idea-lock linkedin-evidence-research linkedin-post-drafter linkedin-humanizer linkedin-visual-producer linkedin-strategy-audit linkedin-publishing-package linkedin-performance-review linkedin-memory-manager linkedin-strategy-review linkedin-governance linkedin-brand-intelligence linkedin-content-intelligence linkedin-anti-repetition linkedin-idea-generation linkedin-idea-selection linkedin-research linkedin-writing linkedin-humanization linkedin-visual-strategy linkedin-visual-production linkedin-visual-qa linkedin-publishing linkedin-measurement linkedin-experiment linkedin-learning linkedin-strategy-learning linkedin-orchestrator"

usage() { echo "Usage: bash uninstall.sh (--global | --project DIR) [--tool claude|codex|all] [--dry-run]"; }

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
      shift ;;
    --dry-run) DRY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ -z "$MODE" ]; then usage >&2; exit 2; fi
if [ ! -d "$SRC/.claude/agents" ] && [ ! -d "$SRC/codex/skills" ]; then
  echo "error: run this from inside a full copy of the repo (needed to know which files to remove)." >&2
  exit 1
fi
DO_CLAUDE=0; DO_CODEX=0
case "$TOOL" in claude) DO_CLAUDE=1 ;; codex) DO_CODEX=1 ;; all) DO_CLAUDE=1; DO_CODEX=1 ;; esac

if [ "$MODE" = "global" ]; then
  DEST_CLAUDE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
else
  DEST_CLAUDE="$TARGET/.claude"
fi

REMOVED=0
[ "$DRY" -eq 1 ] && echo "(dry run - nothing will be deleted)"

if [ "$DO_CLAUDE" -eq 1 ]; then
  echo "Removing Claude Code files from: $DEST_CLAUDE"
  for kind in agents commands; do
    for f in "$SRC"/.claude/$kind/*.md; do
      dst="$DEST_CLAUDE/$kind/$(basename "$f")"
      if [ -e "$dst" ]; then
        echo "  remove    $kind/$(basename "$f")"
        if [ "$DRY" -eq 0 ]; then rm -f "$dst"; fi
        REMOVED=$((REMOVED+1))
      fi
    done
  done
fi

if [ "$DO_CODEX" -eq 1 ]; then
  CODEX_DEST="${CODEX_HOME:-$HOME/.codex}/skills"
  echo "Removing Codex skills from: $CODEX_DEST"
  while IFS= read -r f; do
    rel="${f#"$SRC"/codex/skills/}"
    dst="$CODEX_DEST/$rel"
    if [ -e "$dst" ]; then
      echo "  remove    skills/$rel"
      if [ "$DRY" -eq 0 ]; then rm -f "$dst"; fi
      REMOVED=$((REMOVED+1))
    fi
  done < <(find "$SRC/codex/skills" -type f | sort)
  if [ "$DRY" -eq 0 ]; then
    for d in "$SRC"/codex/skills/*/; do
      n="$(basename "$d")"
      rmdir "$CODEX_DEST/$n/agents" "$CODEX_DEST/$n" 2>/dev/null || true
    done
  fi
fi

# also remove agents from earlier versions of this project
for n in $LEGACY_NAMES; do
  if [ "$DO_CLAUDE" -eq 1 ] && [ -e "$DEST_CLAUDE/agents/$n.md" ]; then
    echo "  remove    legacy agents/$n.md"; if [ "$DRY" -eq 0 ]; then rm -f "$DEST_CLAUDE/agents/$n.md"; fi; REMOVED=$((REMOVED+1))
  fi
  if [ "$DO_CODEX" -eq 1 ] && [ -d "${CODEX_HOME:-$HOME/.codex}/skills/$n" ]; then
    echo "  remove    legacy skills/$n"; if [ "$DRY" -eq 0 ]; then rm -rf "${CODEX_HOME:-$HOME/.codex}/skills/$n"; fi; REMOVED=$((REMOVED+1))
  fi
done

echo "Done: $REMOVED file(s) removed. Your CLAUDE.md, AGENTS.md, docs/, memory/ and runs/ were not touched."
echo "Automation scripts in your workspace scripts/ folder were left in place. To stop automatic runs first run: scripts/register-schedule.sh --remove (Windows: scripts\\register-schedule.ps1 -Remove), then delete scripts/ yourself if you like."
