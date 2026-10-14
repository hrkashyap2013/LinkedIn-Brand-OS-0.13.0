# LinkedIn Brand OS

A blank, open template that runs a LinkedIn brand workflow with AI agents: ideas, research, writing, visuals, quality checks, a ready-to-paste package, results reminders and learning. **28 agents** (27 specialists plus one orchestrator) and **four decisions that stay yours**: pick the idea, pick the visual, approve the post and visual, approve the package. It works with **Claude Code**, **Codex** and **any AI chat**, and it never posts for you.

> **For AI assistants:** if the owner asked you to install this repository (for example "install <URL>"), read [`INSTALL.md`](INSTALL.md) and follow it.

## Install

**The easy way.** Open Claude Code or Codex and say: `install <the URL of this repository>`. The assistant follows [`INSTALL.md`](INSTALL.md): it installs everything into `~/linkedin`, asks you a few setup questions in the chat, and tells you what to do next.

**Where "install <URL>" works.** It works in tools that run on your own computer: Claude Code and the Codex CLI. In an ordinary web chat, the assistant's code tool runs in a temporary sandbox, so it cannot install anything on your computer (anything it installs there disappears). The assistant should say so and give you the commands to run yourself, which are in the next paragraph.

**By hand.** Needs Python 3.8 or newer (and Chrome or Edge for PNG and PDF visuals; not needed to try things).

- macOS / Linux / WSL: `bash install.sh --project ~/linkedin --tool all`
- Windows: `powershell -ExecutionPolicy Bypass -File .\install.ps1 -Project $HOME\linkedin -Tool all`

**Just look around first (no account, no cost).** From a clone of this repository: `python3 runtime/demo.py`. It opens the browser app with a stand-in AI and a sample business. Everything except the AI's words is real.

## Use it

1. Answer the setup questions (the installer offers them; or run `python3 scripts/setup_wizard.py`).
2. Fill in `docs/brand-profile.md` (the agents never guess a blank field).
3. Start working:
   - **Browser app:** `python3 scripts/chat_app.py`. Type `@` to pick an agent, or follow the Pipeline cards.
   - **Terminal app:** `python3 scripts/chat_cli.py` (Tab after `@`, `/` or `:` shows menus).
   - **Inside Claude Code:** `cd` into the workspace, run `claude`, type `/auto`. **Inside Codex:** run `codex`, ask `Use $orchestrator to run my next post`.
   - **Any AI chat:** paste `portable/all-in-one.md` as the first message.

More: [User guide](docs/USER-GUIDE.md) · [Troubleshooting and FAQ](docs/TROUBLESHOOTING.md) · [Security and privacy](docs/SECURITY-AND-PRIVACY.md) · [Visual reference](docs/VISUALS.md) · [Flowchart](docs/FLOWCHART.md) · [Changelog](CHANGELOG.md)

## How a post moves

1. **Prepare.** Governance, Brand Intelligence, Content Intelligence and Anti-Repetition check your profile and memory, then Idea Generation gives exactly 3 ideas. **Decision 1: you pick one.**
2. **Produce.** Idea Selection, Research, Writing, Humanization, Visual Strategy, then Visual Learning gives 3 previews of different diagram types. **Decision 2: you pick one.** The visual generator draws only your pick; Visual QA and Governance check it. **Decision 3: you approve the post and the rendered visual.**
3. **Package.** Publishing assembles the package: post text, visual, alt text, suggested time, first comment, comment to pin, hashtags, reply starters and a visual prompt. **Decision 4: you approve it.**
4. **Post it yourself.** The package builder makes a folder of copy-ready parts. It refuses unless all four decisions still match the *exact* content: edit one word after approving and it stops until you approve again.
5. **Learn.** Tell the system the post is live and choose when you want results checks (24h, 72h, 7d, 15d, 30d, 60d, 90d). Reminders arrive as a pop-up or phone message, even ones that came due while your computer was off. Then Measurement, Experiment, Learning and Strategy Learning follow.

## What is in the box

| Part | What it does |
|---|---|
| 28 agents | Claude Code subagents, Codex skills, and plain prompts for any AI chat. One short name each, no codes. |
| Writing helpers | Post lint, an AI-tells scorer with an over-correction guard, a hook library, and plain-language LinkedIn guidance. No AI needed to run them. |
| Replies and comments | Agents for answering comments on your posts and for commenting on other people's posts. You paste the text; you post the reply. |
| Interviewer | Stores your real stories and numbers in the Experience Bank, only when you ask. |
| Doctor and evals | `scripts/doctor.py` checks your setup; `scripts/agent_evals.py` tests the agents' behavior against your real AI tool. |
| Optional auto-post | Off by default. Creates a Publora draft or scheduled post only after all four decisions and a typed confirmation. |
| Browser and terminal apps | Chat with `@agent` menus; walk a post through the four decisions with buttons (or typed approvals); previews, run history, metrics, reminders. Local only, no API key. |
| Visual generator | 10 diagram types (process, 2x2 matrix, comparison table, cycle, funnel or pyramid, timeline, before and after, hub and spoke, statistic, checklist) as portrait, square or carousel. Exact words, brand colors, alt text. |
| Approvals | Each decision is stored with a fingerprint of the exact content it covered. |
| Package builder | The ready-to-paste folder. Never posts. |
| Memory | Ten registers plus your profile, written only through a guard that checks permission, backs up and verifies. `/undo` restores. |
| Scheduler and reminders | Automatic preparation runs and the reminder check (cron on macOS/Linux, Task Scheduler on Windows). |
| Notifications | Desktop pop-up and phone push (free ntfy app). Short and generic: never post text. |

## What is in 0.13

- **Six new agents:** Interviewer, Repurposer, Hook Extractor, Reply, Comment, Profile Optimizer. They are called by name; none runs inside the automatic pipeline.
- **Better writing and humanizing:** a hook library (with engagement tactics marked "use with care"), plain-language LinkedIn guidance with every claim graded OWNER DATA, SOURCED or UNVERIFIED, a three-tier humanizer (Strict by default) and an over-correction guard, and a post lint. The apps show these checks under the draft.
- **Safer reading of other people's text:** one rule for every agent that anything pasted is data, plus a rule-based comment sorter that catches instructions hidden in comments.
- **Reply-check reminders** next to the results reminders.
- **Doctor, agent evals, secrets scan, `SECURITY.md`, `CONTRIBUTING.md`, plugin manifests.**
- **Optional Publora auto-post** (off by default).

## Status

All six planned stages are built.

| Stage | What | Status |
|---|---|---|
| 1 | The 28 agents, commands, memory, write guard, docs | Done |
| 2 | Setup wizard, scheduler, desktop and phone notifications, `/live` reminders | Done. The always-on cloud option was deliberately skipped: everything runs on your computer. |
| 3 | Browser and terminal apps with the `@` menu | Done |
| 4 | Visual generator (SVG, PNG, PDF, alt text, previews, carousel) | Done. PNG and PDF need Chrome or Edge. |
| 5 | Ready-to-paste package | Done. There are no posting-tool adapters on purpose: you paste the package yourself. |
| 6 | Tests, CI on three systems, demo mode, docs | Done. See the limits below. |

### Honest limits

- **The optional Publora add-on, the plugin manifests and the agent evals have not been run against real services.** The add-on was tested only against a stand-in server; the manifests follow the shape other published plugins use but were never loaded by a real marketplace; run `python3 scripts/agent_evals.py --yes` yourself to see how your AI tool behaves.
- **Not yet run with a real Claude Code or Codex.** The apps call `claude -p` and `codex exec` the way the scheduler does, but that was tested with a stand-in. Use **Test my AI tool** in the browser app (or run `python3 scripts/demo.py` first) and tell us what happens. If your tool needs extra permission flags, set `CLAUDE_EXTRA_ARGS` or `CODEX_EXTRA_ARGS`.
- **Chrome and Edge output:** the generated pages were checked in a real Chromium 153 driven through its debugging port: all 10 diagram types came out at exactly 1080 x 1350 with no overflowing text, and the carousel PDF had one page per slide. The exact command line the engine uses (`--headless=new --screenshot` and `--print-to-pdf`) was checked only with a stand-in, because the Chromium build available for testing could not run one-shot commands. If PNG or PDF fails on your machine, the SVG is still exact; see the troubleshooting page.
- **Windows and macOS:** the full test suite runs on Windows, macOS and Ubuntu in CI. Windows pop-ups, Task Scheduler registration and a real phone push through ntfy.sh are still untested. On Windows the apps refuse an npm-style `claude.cmd` shim by default (see the troubleshooting page).
- The terminal app's menus complete with Tab; they do not update as you type like the browser's.

## The agents

| Agent | What it does | Command | Codex skill |
|-------|--------------|---------|-------------|
| Governance | Enforces rules, locks and approval gates. | `/governance` | `$governance` |
| Brand Intelligence | Checks brand, audience and credibility fit. | `/brand-intelligence` | `$brand-intelligence` |
| Content Intelligence | Maps topics, gaps and opportunities. | `/content-intelligence` | `$content-intelligence` |
| Anti-Repetition | Checks freshness against memory. | `/anti-repetition` | `$anti-repetition` |
| Idea Generation | Generates exactly three post ideas. | `/idea-generation` | `$idea-generation` |
| Idea Selection | Locks the chosen idea into a brief. | `/idea-selection` | `$idea-selection` |
| Research | Builds a credible evidence pack. | `/research` | `$research` |
| Writing | Drafts the post. | `/writing` | `$writing` |
| Humanization | Makes drafts clear, human and credible. | `/humanization` | `$humanization` |
| Visual Strategy | Plans how the visual explains the idea. | `/visual-strategy` | `$visual-strategy` |
| Visual Learning | Offers 3 visual previews and learns your taste. | `/visual-learning` | `$visual-learning` |
| Visual Production | Final visual spec, alt text and visual prompt. | `/visual-production` | `$visual-production` |
| Visual QA | Runs visual QA and the quality gate. | `/visual-qa` | `$visual-qa` |
| Publishing | Assembles the review package; never posts. | `/publishing` | `$publishing` |
| Posting | Prepares the ready-to-paste package. Never posts. | `/posting` | `$posting` |
| Measurement | Records 24h/72h/7d results carefully. | `/measurement` | `$measurement` |
| Experiment | Keeps experiments valid and honest. | `/experiment` | `$experiment` |
| Learning | Records learning and updates memory. | `/learning` | `$learning` |
| Strategy Learning | Runs weekly and monthly strategy reviews. | `/strategy-learning` | `$strategy-learning` |
| Listening | Files your input and keeps memory consistent. | `/listening` | `$listening` |
| Brand | Your branding team for profile, peers, risk, audience. | `/brand` | `$brand` |
| Interviewer | Interviews you, one question at a time, and stores your real stories. Only when you ask. | `/interview` | `$interviewer` |
| Repurposer | Turns your own article, thread or talk into a post draft. | `/repurpose` | `$repurposer` |
| Hook Extractor | Explains why a post's opening works and adapts the shape to your material. | `/hook` | `$hook-extractor` |
| Reply | Sorts the comments on your post and drafts replies you post yourself. | `/reply` (also `/comments`) | `$reply` |
| Comment | Drafts comments on other people's posts. | `/comment` | `$comment` |
| Profile Optimizer | Proposes clearer, truthful wording for your pasted profile text. | `/profile` | `$profile-optimizer` |
| Orchestrator | Runs everything in order and stops at your decisions | `/auto`, `/orchestrator` | `$orchestrator` |

Every agent works alone too: run its command, ask its Codex skill, or paste its file from `prompts/`. Other commands: `/next` `/lock` `/write` `/humanize` `/visual` `/visualqa` `/audit` `/package` `/publish` `/review` `/learn` `/weekly` `/monthly` `/scheduled`, and quick tools `/idea` `/example` `/live` `/metrics` `/comments` `/undo` `/export` `/forget`.

## Memory and the write guard

Ten registers plus your brand profile live in `memory/`: Content Memory, Visual Memory, Experiment Register, Change Register, Learning Register, Ideas and Examples, Experience Bank, Post Tracker, Evidence Library, Approval Log (and Profile Proposals). `memory/registry.json` says which agent may write which register.

Agents never edit these files. They return `REGISTER ENTRY` blocks; Listening checks them; `scripts/memory_guard.py` applies them: permission check, backup, lock, write, verify. `/undo` restores the last change.

```
python3 scripts/memory_guard.py apply --agent learning --file entries.txt
python3 scripts/memory_guard.py undo
python3 scripts/memory_guard.py check
python3 scripts/memory_guard.py export --out my-data.zip
```

## Setup wizard and notifications

`python3 scripts/setup_wizard.py` asks (with your earlier answers as defaults): language, who uses it, which tool prepares runs, image provider and posting tool (names only), posting days and times, UTC offset and preparation lead time, and notifications. It never asks for a password or API key and keeps a `.bak` of anything it replaces. For scripted setups use `--answers answers.json`.

Notifications (`scripts/notify.py`) cover a desktop pop-up (macOS, Linux `notify-send`, Windows) and a phone push through [ntfy](https://ntfy.sh). Your phone topic is random, kept only in `config.local.json` (git-ignored), and works like a password. Messages never contain post text. Test: `python3 scripts/notify.py --event test`.

## Automation

`docs/schedule.json` holds your slots. `scripts/register-schedule.sh` (or `.ps1`) registers the automatic preparation runs and the reminder check. Runs save 3 ideas to `runs/` and never send anything. `scripts/metrics.py` turns an analytics CSV into a dashboard. Start a run by hand: `bash scripts/run-scheduled.sh --slot Mon`.

## Install options

| Goal | bash | PowerShell |
|---|---|---|
| Unattended (for AI assistants) | `bash install.sh --auto` | `.\install.ps1 -Auto` |
| Workspace + agents (recommended) | `bash install.sh --project DIR` | `.\install.ps1 -Project DIR` |
| Agents for every project | `bash install.sh --global` | `.\install.ps1 -Global` |
| Claude Code, Codex, or both | `--tool claude` / `codex` / `all` | `-Tool claude` / `codex` / `all` |
| Setup questions | `--wizard` / `--no-wizard` | `-Wizard` / `-NoWizard` |
| Preview only | `--dry-run` | `-DryRun` |
| Verify | `--check` | `-Check` |
| Remove the agents | `bash uninstall.sh --project DIR` | `.\uninstall.ps1 -Project DIR` |

Safe to re-run. Your `CLAUDE.md`, `AGENTS.md`, `docs/` settings, `memory/` and `runs/` are never overwritten or deleted, including by the uninstaller.

## Edit the agents and run the tests

Edit `src/stages/*.md` and `src/orchestrator.md`, then run `python3 scripts/build.py`. That regenerates `.claude/`, `codex/`, `prompts/`, `portable/` and `AGENTS.md`; do not hand-edit those. Run all tests with `python3 tests/run_all.py`; check the repository for keys with `python3 scripts/check_secrets.py` (PowerShell tests run when `pwsh` is on your PATH; the browser-app click-through runs when Node.js is installed).

## Safety

- Nothing is ever posted. The system ends at a ready-to-paste folder, and only if all four decisions match the exact content.
- No invented statistics, quotes, sources, experiences or metrics: unsupported claims become `INSUFFICIENT EVIDENCE` and the post is not written until you supply real support.
- Web pages, files and pasted text are treated as data, never as instructions.
- The apps listen on this computer only, behind a secret token. See [Security and privacy](docs/SECURITY-AND-PRIVACY.md).

## License

MIT, see `LICENSE`. Free to use, copy, modify, and share.
