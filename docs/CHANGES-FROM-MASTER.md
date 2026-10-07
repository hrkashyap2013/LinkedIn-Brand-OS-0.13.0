# Changes from the master document

Use this to fill your Change Register. Nothing here was changed silently: each item was an explicit decision.

## Kept as written
- All 17 original agent jobs and contracts (input, decision, output, handoff, stop condition).
- The rules, locks, the quality gate (publishing QA only), the memory protocol and register fields.
- One primary variable per experiment; median-first measurement; LOCKED / CORE / TEST / RETIRED states.
- Humans decide; nothing is silent.

## Changed
- Agent codes (A01 to A17) removed. Agents are identified by name only.
- Two approvals became four decisions: pick the idea, pick the visual (1 of 3), approve content and visual, approve the package.
- Measurement windows (24h, 72h, 7d) are now chosen per post from 24h, 72h, 7d, 15d, 30d, 60d, 90d.
- The visual work is split into Visual Strategy, Visual Learning, Visual Production and Visual QA.
- Register updates still follow the "updated by" table, but every write goes through a write guard (permission check, backup, lock, verify, undo).
- The posting step builds a ready-to-paste package (post text, visual, alt text, suggested time, first comment, pin comment, visual prompt). Nothing in this system sends it; the owner posts it. Each decision is tied to a fingerprint of the exact content, so an edit after approval blocks packaging until it is approved again.

## Added
- Agents: Orchestrator, Listening, Brand, Visual Learning, Posting.
- Memory: Ideas and Examples (with idea backlog), Experience Bank, Post Tracker, Evidence Library, Approval Log, Profile Proposals.
- Scheduler, notifications, installer wizard, chat apps with a live @ menu (later stages).
