# Runtime scripts

These are copied into your workspace's `scripts/` folder by the installer.

| File | What it does |
|---|---|
| `chat_app.py` (+ `app/`) | The browser app: chat with an `@` agent menu, the four-decision pipeline, previews, runs, metrics. Local only. |
| `chat_cli.py` | The same in the terminal (Tab menus; you type APPROVE for decisions). |
| `chat_core.py` | The engine both apps share (AI runner, prompts, pipeline). Not run directly. |
| `demo.py`, `demo_ai.py` | Try everything with a stand-in AI and a sample business. No account, no cost. |
| `visual_engine.py` | Draws visuals from a JSON spec: SVG, PNG, PDF, alt text, previews, carousel. |
| `postkit.py` | One post's files, package fields, fingerprints, `live`. |
| `approvals.py` | Records and verifies your four decisions against the exact content. |
| `package_builder.py` | Builds the ready-to-paste folder (only if all four decisions match). Never posts. |
| `reminders.py` | Results-check reminders (`/live`), including ones missed while the computer was off. |
| `setup_wizard.py` | Asks the setup questions; writes `docs/settings.json` and `docs/schedule.json`. |
| `notify.py` | Desktop and phone (ntfy) notifications. Short and generic. |
| `post_lint.py` | Checks a draft for writing and hygiene problems (no AI). Errors, warnings and notes. |
| `ai_tells.py` | Scores machine-like patterns at three tiers and guards against over-correction (`compare`). No AI. |
| `reply_filter.py` | Rule-based first sort of pasted comments, including ones that try to instruct an AI. Posts nothing. |
| `doctor.py` | Checks your setup and says how to fix each problem. `--test-ai` makes one tiny AI request. |
| `agent_evals.py` | Tests the agents' behavior against your real AI tool with code-based graders. Needs `--yes`. |
| `publish_publora.py` | OPTIONAL, off by default: creates a Publora draft or scheduled post after all four decisions and a typed confirmation. |
| `image_provider.py` | A socket for an AI image provider (none connected). |
| `run-scheduled.sh` / `.ps1` | Prepares 3 ideas for a slot and saves them to `runs/`. Never publishes. |
| `register-schedule.sh` / `.ps1` | Registers (or removes) the preparation runs and the reminder check. |
| `scheduled-prompt.md` | The unattended instructions the runner sends to Claude Code or Codex. |
| `memory_guard.py` | The only way agents write memory: permission, backup, lock, verify, undo. |
| `metrics.py` | Turns a LinkedIn analytics CSV export into the 6-panel dashboard. |

Start the app: `python3 scripts/chat_app.py`. Try it with no AI: `python3 scripts/demo.py`.
