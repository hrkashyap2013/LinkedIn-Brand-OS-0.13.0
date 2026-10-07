# Troubleshooting and FAQ

## The app or AI

**"The 'claude' command was not found on PATH."** Install Claude Code (or Codex) and sign in, then start the app from a new terminal window. Or try the demo: `python3 scripts/demo.py`.

**The AI step times out or stops with an error.** Click **Test my AI tool** in the browser app: it shows the tool's own message. The apps run `claude -p "<request>"` or `codex exec "<request>"`. If your tool needs permission flags or a model option, set `CLAUDE_EXTRA_ARGS` or `CODEX_EXTRA_ARGS` before starting the app (for example `export CLAUDE_EXTRA_ARGS="--model <name>"`). The AI only returns text, so it should not need permission to run commands or edit files. Raise the time limit with `LBA_AI_TIMEOUT=1800` (seconds).

**"The AI's answer could not be used after a retry."** The AI did not return the JSON the step needs, twice. Run the step again, or add feedback ("keep labels to six words"). Nothing half-valid is ever saved.

**"The request is too large."** Your brand profile and memory are long. The app already shortens its excerpts; shorten `docs/brand-profile.md` (remove explanations, keep facts) and try again. The limit protects Windows, whose command line is limited to about 32,000 characters.

**The browser did not open.** Open the link printed in the terminal. It contains a secret token and only works on this computer.

**"Forbidden host" or "Open the link that the terminal printed".** Use the exact link from the terminal (`http://127.0.0.1:<port>/?t=...`). Other addresses, and old links from a previous run, are refused on purpose.

## Visuals

**I only get SVG, no PNG or PDF.** No Chrome or Edge was found. Install one, or set `LBA_BROWSER` to the full path of a Chromium-based browser (`python3 scripts/visual_engine.py browser` shows what was found), then render again. Meanwhile the `.html` file next to the SVG opens in any browser; use Print, Save as PDF.

**A warning says text is too small or too long.** The generator never shrinks type below 28 px and never lets text spill out. Use fewer words, or fewer items, or split into a carousel.

**Colors look wrong or a contrast warning appears.** Check the hex values in section 11 of `docs/brand-profile.md` (six digits like `#1F3A5F`). Very light colors on a white background fail the 4.5:1 readable minimum.

**My font is ignored.** Use a font installed on your computer and write only letters, digits and spaces. Other computers may show a different font if they lack it; the SVG falls back to Helvetica or Arial.

## Decisions and packages

**A decision says "changed, approve again".** Something covered by it changed after you approved (a word in the post, a package field, the visual). That is the system working. Review, then approve again. Changing it back restores the old approval.

**"Decision N is missing" when building.** Approve it first. A package is only built when all four match.

**I approved in chat with Claude Code, but the app does not show it.** Chat approvals are recorded in the Approval Log with your words. They do match if the fingerprint is the same. The apps' buttons are the stronger route because an AI cannot press them.

## Notifications and reminders

**No pop-up on Linux.** Install `libnotify-bin` (Debian and Ubuntu). **No phone message:** install the ntfy app, subscribe to the exact topic the wizard printed, and run `python3 scripts/notify.py --event test` to see the reason.

**A reminder never arrived.** Open **Runs and reminders**: due checks stay listed until you mark them done. Check the scheduler is registered (`crontab -l` should show a `linkedin-brand-agents` block; on Windows open Task Scheduler and look for `LinkedInBrand-Reminders`). Re-run `register-schedule` after changing time zone or daylight saving.

## Writing checks, replies and the interview

**The checks flag something I want to keep.** Warnings are guidance, not rules. Errors (a leftover placeholder, empty text) should be fixed. A shouted opening, announced candor or an engagement tactic is your call; Governance may still note it.

**The humanizer made my post flatter.** Run `python3 scripts/ai_tells.py compare --before <original> --after <edited> --signature "a phrase you always use"`. It reports changed figures, quotations or links, dropped signature phrases, lost sentence variety and big cuts. Ask for the Forensic strength only if Strict is too heavy for your voice (`humanizer_tier` in `docs/settings.json`).

**The Reply agent skipped or flagged a comment I wanted to answer.** It flags hostile, legal, medical, financial or personal-data content and anything that tries to instruct an AI; the sorting is a first pass. Tell it you want that comment answered and why, or answer it yourself.

**The interviewer never starts.** It runs only when you ask: `/interview`, or `@interviewer` in the apps. Saving needs you to say the story is true and usable; then the entry goes through the write guard.

## Doctor and evals

**What do WARN and FAIL mean?** WARN: it works but something is missing or off (for example no Chrome or Edge). FAIL: something is broken (for example the AI tool is not found). Every line has a suggested fix. Run `python3 scripts/doctor.py`.

**An eval case failed.** Run it again alone: `python3 scripts/agent_evals.py --yes --only <case-id> --show`. If it keeps failing, your AI tool is not following that agent's rule; please report it with the case id.

## The optional Publora add-on

**"Auto-post is off."** Turn it on in `docs/settings.json` (and set `PUBLORA_API_KEY`) only if you really want it. **"Build the ready-to-paste package first."** All four decisions must match and the package must be built from the current content. **"This package has a visual, but the Publora API takes pictures only as a public web link."** Pass `--media-url` with a public https link to the image, or `--text-only` and add the image by hand.

**"This package is locked."** An earlier send ended unclearly. Open Publora, check whether anything was created for this post, and only if nothing was, run `python3 scripts/publish_publora.py forget --id P-...` at a keyboard.

## Windows notes

Use `python` instead of `python3`, and PowerShell commands from the README. If scripts are blocked, run them with `-ExecutionPolicy Bypass` as shown. The installer needs no administrator rights.

## FAQ

**Does it post for me?** No. It builds a folder you copy from. There is no LinkedIn login and no posting tool.

**Does it need an API key?** No. It uses the Claude Code or Codex you already have. The setup asks only for names, never keys.

**Where is my data?** In your workspace folder on your computer. Nothing is uploaded by this software. Your AI tool sends the text of each request to its own provider, as it does whenever you use it.

**Can an agent invent a statistic?** The rules forbid it and the post is not written until you supply real support, but no software can promise an AI never errs. The checks and your four decisions are the safety net: read what you approve.

**Can I use another language?** Yes: set it in the wizard. Visual text in languages other than English-like Latin scripts depends on fonts installed on your computer, and was not tested.

**How do I update?** Download or pull the new version and run the installer again. Agents and scripts update in place (with `.bak` copies if you edited them); your own files are untouched.

**How do I report a problem?** Open an issue on the repository with the version (the `VERSION` file) and the exact message. Do not paste your brand profile or any keys.
