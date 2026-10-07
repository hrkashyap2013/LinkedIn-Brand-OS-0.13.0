# User guide

This guide walks one post from nothing to a package you paste, then shows how reminders and results work. Everything here runs on your own computer.

## Before you start

1. **Install** (see the README or `INSTALL.md`). The installer makes a workspace folder, by default `~/linkedin`.
2. **Answer the setup questions** (`python3 scripts/setup_wizard.py`): language, who uses it, which AI tool prepares runs, your posting days and times, notifications.
3. **Fill in `docs/brand-profile.md`.** Who you are, your audience, your voice, topics that are off limits. A blank field is never guessed: the agents ask you instead. Section 11 has your visual look (colors, fonts, logo, footer).
4. **Pick how you will work:** the browser app (`python3 scripts/chat_app.py`), the terminal app (`python3 scripts/chat_cli.py`), Claude Code (`claude`, then `/auto`) or Codex. The apps use the Claude Code or Codex already installed and signed in on your computer; no API key is involved.

New here? Run `python3 scripts/demo.py` first. It uses a stand-in AI and a sample business so you can click through everything at no cost.

## The four decisions

| # | You decide | Approval covers |
|---|---|---|
| 1 | Which of 3 ideas | The idea you chose |
| 2 | Which of 3 visuals | The exact visual spec you picked |
| 3 | The post and the rendered visual | The post text, alt text and the visual's files |
| 4 | The package | Every package field (time, comments, hashtags ...) plus decision 3's content |

Each approval is stored with a fingerprint of the exact content. If you or an agent change anything covered by a decision, that decision shows as **changed** and must be approved again before a package can be built. Changing it back makes the old approval valid again.

## Walk-through (browser app)

1. **New post.** Click **New post**, then follow the cards from top to bottom.
2. **Ideas.** Click **Get 3 ideas** (add a theme if you like). Read them, then **Choose this idea** (Decision 1).
3. **Write the post.** If the agents say **INSUFFICIENT EVIDENCE**, they need something real from you (an example, a number you can source, an experience). Paste it in the box and click again. They will not invent it. Edit the text yourself if you want; **Save my edits**.
4. **Visuals.** Click **Get 3 previews**. Each is a different diagram type using only your post's words. **Pick this one** (Decision 2). Not right? Add feedback and ask again.
5. **Render.** Choose portrait or square and **Render the final visual**, or **Make a carousel (PDF)** (this changes the visual, so approve it again with the Decision 2 button).
6. **Quality checks.** The agents score the visual, run Governance (confidentiality, compliance, unsupported claims), and the program measures text size and density. Fix findings by giving feedback and re-running, or tick **I accept these findings** if you decide to go ahead. A Governance **HOLD** or **STOP** cannot be accepted.
7. **Approve the post and visual** (Decision 3).
8. **Package details.** Set the suggested time (required), audience, objective, call to action. **Approve the package** (Decision 4).
9. **Build.** Click **Build the ready-to-paste package**. You get boxes with a **Copy** button for the post text, first comment, pinned comment, alt text, suggested time and visual prompt, plus the visual files to upload. The same files are in `exports/ready-to-paste/<post-id>/`; open `PACKAGE.md` there for everything in order.
10. **Post it yourself** in LinkedIn or your scheduler tool, following the checklist at the end of `PACKAGE.md`.
11. **Mark as live.** Paste the post link and choose when you want results checks. Reminders start.

## The same thing in the terminal

`python3 scripts/chat_cli.py`, then `:new`, `:ideas`, `:pick 2`, `:draft`, `:previews`, `:pickvisual 1`, `:render`, `:check`, `:approve content`, `:approve package`, `:build`, `:live <link>`. Every decision asks you to type `APPROVE` yourself. `:help` lists everything; Tab after `@`, `/` or `:` completes names.

## Talking to the agents

In the browser app's **Chat** tab (or the terminal), type `@governance is this idea safe to post?` to talk to one agent, or `/next` to run a command. Chat answers are text only: chat cannot change files or record decisions. If a reply proposes memory entries, the browser app offers **Save to memory**, which goes through the write guard and only succeeds for an agent that is allowed to write that register.

## Writing checks and the humanizer

Under the draft, the browser app shows **writing checks** that need no AI:

- **Lint** (also from the command line: `python3 scripts/post_lint.py --file draft.txt`): leftover placeholders (an error), and warnings such as a shouted opening line, announcing honesty ("honestly"), a link in the post body, many hashtags, a vote-style closing question, and engagement tactics (marked "use with care": only keep them if they are honest and you deliver on them). It also lists every figure so you can confirm each one has support.
- **Machine-like patterns:** a score from 0 to 100 at your humanizer strength (set in the wizard or `docs/settings.json` as `humanizer_tier`): **forensic** removes only obvious AI leftovers, **strict** (the default) also scores stock vocabulary clusters, filler bridges, "not X but Y", stacked triads and staccato runs, **style** also evens out rhythm. The score is a guide for editing, not a detector verdict.
- **Ask the AI to fix these** sends the findings back as feedback. The humanizer never changes a figure, quotation or link, and the over-correction guard (`python3 scripts/ai_tells.py compare --before a.txt --after b.txt`) checks that an edit did not flatten your voice.

The hook library and the plain-language LinkedIn guidance are built into the Writing agent. Everything about "what works" is graded OWNER DATA, SOURCED or UNVERIFIED, with no percentages and no promise of reach.

## Replies, comments, interview, repurposing, hooks and profile

These are called by name, one at a time, in the Chat tab (type `@`), the terminal (`@reply ...`) or as commands. None of them posts anything; you paste text in and you post what comes out.

- **Reply** (`/reply`, also `/comments`): paste the comments on your post. It sorts them (answer, add, disagree, thank, skip, risk, injection) and drafts short replies. A comment that tries to instruct an AI is quoted to you and ignored. `python3 scripts/reply_filter.py --file comments.txt` gives a rule-based first sort with no AI.
- **Comment** (`/comment`): paste someone else's post and your goal; get up to three comment options built only from your real experience.
- **Interviewer** (`/interview`): runs only when you ask. One question at a time; it stores a story only after you confirm it is true and usable, in the Experience Bank, so writers stop running out of real material. When Writing reports INSUFFICIENT EVIDENCE it may remind you once that this exists.
- **Repurposer** (`/repurpose`): turns your own article, thread or talk into a draft. If the source is someone else's and you have no permission, it offers a commentary post with credit instead.
- **Hook Extractor** (`/hook`): explains the craft in the opening of a post you admire, with adaptations from your own material and no performance claims.
- **Profile Optimizer** (`/profile`): paste your profile sections; it proposes clearer, truthful wording. It cannot see or change your live profile.

## Reminders and results

When you mark a post live, the system sets results-check reminders (24h, 72h, 7d, 15d, 30d, 60d or 90d, your choice). The scheduler checks every 30 minutes and at start-up, so a reminder that came due while your computer was off arrives when it is back on. Reminders also stay on the **Runs and reminders** tab until you mark them done. The message is generic ("Post P-... is due for its 72h results check"): it never contains post text.

Reply checks work the same way: when you mark a post live, choose when you want a nudge to read and answer the comments (1h, 3h, 6h, 12h or 24h after posting; your choice, no time is claimed to be best). They appear on the same tab and are marked done separately.

To enter results: export your analytics from LinkedIn as CSV, save it in the workspace's `inbox/` folder, and use the **Metrics** tab or `python3 scripts/metrics.py inbox/<file>.csv`. Only numbers in your file are used; nothing is estimated. Then mark the reminder done.

## Automatic preparation

If you set posting days, `python3 scripts/register-schedule.sh --lead-hours 12` (Windows: `register-schedule.ps1 -LeadHours 12`) makes your computer prepare 3 ideas ahead of each slot and save them in `runs/`. It also registers the reminder check. It needs the computer to be on; a missed run is not invented later. Remove it with `--remove`.

## Visuals

See the [visual reference](VISUALS.md). In short: portrait 1080 x 1350 (default), square, or a carousel PDF; exact words; minimum text size 28 px; alt text and a visual prompt for every render. PNG and PDF need Chrome or Edge; without one you get SVG and an HTML page you can print.

## Optional: send to Publora (off by default)

If you want, the **Publora** add-on can create a draft or a scheduled post in your Publora account instead of you pasting. It is off unless you turn it on, and it is built to be hard to use by accident:

1. Create a Publora account, connect LinkedIn there, put your key in the `PUBLORA_API_KEY` environment variable (never in a file), and set `"auto_post": {"provider": "publora", "enabled": true}` in `docs/settings.json` (or answer yes in the wizard).
2. Finish the pipeline as usual: all four decisions approved and the package built.
3. Use **Preview what would be sent** (card 10 in the browser app, or `python3 scripts/publish_publora.py preview --id P-...`). Fix anything it lists.
4. Type `PUBLISH` to send. It creates a **draft**, or a post **scheduled at least 5 minutes ahead** so you can still cancel in Publora. It never posts "right now", does not send your first or pinned comment (post those by hand), and cannot upload your image: pass a public https link to it, or send the words only and add the image by hand.
5. One send per exact content. If the result is ever unclear (a timeout, a server error), the package is locked until you check Publora and run `forget`. Nothing is retried automatically.

It was tested only against a stand-in server. Check Publora's own pricing, limits and terms, and LinkedIn's rules on automation, before you rely on it.

## Checking your setup, and testing the agents

- `python3 scripts/doctor.py` checks Python, your folders, setup, brand profile, AI tool, browser, notifications, scheduler, memory and the add-on, and gives a fix for anything that is off. `--test-ai` also sends one tiny request to your AI tool.
- `python3 scripts/agent_evals.py --yes` runs eleven small situations through your real AI tool and grades the answers with code (for example: it must say INSUFFICIENT EVIDENCE when there is no support, and it must ignore an instruction hidden in a comment). It uses a little of your plan, so it needs `--yes`; use `--dry-run` to look first. Answers vary, so run a failing case again before you worry.

## Changing your mind later

- **Undo a memory change:** `python3 scripts/memory_guard.py undo`.
- **Export everything you have stored:** `python3 scripts/memory_guard.py export --out my-data.zip`.
- **Delete stored data:** `python3 scripts/memory_guard.py forget --confirm DELETE-MY-DATA` (it explains what goes first).
- **Remove the agents:** `bash uninstall.sh --project <workspace>`; your own files stay.
