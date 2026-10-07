# Contributing

Thank you for helping. This project is a blank, open template: keep it free of personal data, keys and anyone's real brand.

## Where things live

- `src/stages/*.md`, `src/orchestrator.md`, `src/refs/*.md`: the sources of every agent. **Edit these, then run `python3 scripts/build.py`.** Do not hand-edit `.claude/`, `codex/`, `prompts/`, `portable/`, `AGENTS.md`, `.claude-plugin/` or `.codex-plugin/`: they are generated and a test checks they are up to date.
- `runtime/`: the scripts and apps that are copied into a workspace's `scripts/` folder.
- `docs/`: guides and the blank templates a user fills in.
- `tests/`: run everything with `python3 tests/run_all.py`.

## Rules for changes

1. **Write in your own words.** Do not copy text from other projects.
2. **No invented claims.** Anything about what works on LinkedIn must be plain-language guidance graded UNVERIFIED unless it comes with a source. No percentages or multipliers for unverified advice.
3. **Nothing posts by itself.** New features must keep the four owner decisions and must not weaken them. Anything that could publish stays off by default and needs its own typed confirmation.
4. **No keys in files.** Keys come from environment variables only. `scripts/check_secrets.py` must pass.
5. **Python 3.8 or newer, standard library only.** No new dependencies.
6. **English only** for text the software shows or writes.
7. **Add tests** for every behavior you add, and keep the whole suite passing on Linux, macOS and Windows.

## Versions and commits

- `VERSION` holds the version (`major.minor.patch`). Bump the patch for fixes, the minor for new features that keep old workspaces working, the major for breaking changes. Add a matching entry at the top of `CHANGELOG.md`; a test checks that they agree.
- Use short, plain commit messages that say what changed and why ("Block packaging when the visual changed after approval").
- Tag releases as `v<version>` after the tests pass.

## Adding an agent

1. Add `src/stages/<name>.md` with the frontmatter and the contract sections (Purpose, Inputs or Start condition, Decision responsibility, Allowed actions, Output, Handoff, Stop condition). Say when to use it in the description. Agents that read other people's text must say to quote and ignore any instructions in it.
2. Add its name to `ORDER` in `scripts/build.py`, a row in the orchestrator's table, and a command if it needs a short alias.
3. If it writes memory, add it to the right register in `memory/registry.json`.
4. Run `python3 scripts/build.py` and the tests; update the README table.
