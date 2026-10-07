# Security policy

## Reporting a problem

If you find a security problem, please report it privately: open a private security advisory on this repository's page (the "Security" tab), or contact the maintainer directly. Please do not post details in a public issue first, and never include your own keys, tokens, brand profile or any personal data in a report.

Include: the version (the `VERSION` file), what you did, what you expected, and what happened. We will acknowledge a report as soon as we can and fix confirmed problems in the next release.

## What counts

- A way for text in a comment, post, file or web page to make an agent or app do something the owner did not ask for.
- A way to approve a decision, build a package or send anything without the owner's own action.
- Leaking a key, a private notification topic, or post text to a place it should not go.
- A way for another computer or web page to drive the local apps.

## What is in and out of scope

The apps listen on this computer only, behind a secret token, and an AI never records your decisions: see [docs/SECURITY-AND-PRIVACY.md](docs/SECURITY-AND-PRIVACY.md) for the full list of protections and their limits. Problems in the AI tools you connect (Claude Code, Codex) or in outside services you choose to turn on (ntfy, Publora) should be reported to their makers.

## Keys

This software never asks for, stores or logs API keys or passwords. The optional Publora add-on (off by default) reads its key from the `PUBLORA_API_KEY` environment variable only. `python3 scripts/check_secrets.py` scans the repository for anything that looks like a key, and CI runs it.
