# market-research-agents

FastAPI + LangGraph 4-agent market-research council (Scout→Astra→Vera→Cleo) with React frontend. See PRD.md for product context.

## Power Coding (auto — do not remove without asking the user)
At session start read Handoff.MD; FIRST run `git log --oneline <its last-synced sha>..HEAD`
and reconcile anything changed underneath it; then open with its pending points. Update
Handoff.MD before every git checkpoint commit and at the end of every phase (low context is
a secondary trigger) — snapshot not journal, re-stamp `last-synced` with HEAD; then, if
context was the trigger, tell the user to start fresh ("Refer to Handoff.MD in
/Users/anandpareek/Documents/market-research-agents and begin"). When Handoff exceeds ~40
lines or ~15 ✅ items, collapse ✅ into one "Shipped:" line, detail to Learning.MD.
Log flow changes / user-reported bugs in Learning.MD (5-whys entry format).
Read Loop.MD every session and obey its `status:` machine — when the first working
draft is done, ASK the user whether to turn the loop on (disclosing the free/paid eval
split); while `status: on`, run the FREE Loop.MD evals after every meaningful change
and report per-eval pass/fail. The golden set / paid evals run ONLY per
consent.paid_evals (ask by default — offer at milestones, never auto per-change).
Keep docs/mermaid/*.mmd current when the flow changes.
Obey .power-coding/config.json FMEA triggers: on_pre_commit ALWAYS runs the secret scan
first (`node ~/.claude/skills/power-coding/scripts/secret-scan.mjs --staged`) and BLOCKS
the commit on a hit, then a light FMEA on the staged diff (P0 → block and ask; per the
user's standing rule, fix P0 only — P1/P2 inform only); smart_suggest: offer a scan at a
natural pause when signals fire, never twice for an unchanged HEAD. FMEA is pinned to a
sha; re-stamp state.last_fmea_commit after.
Sentinel is enabled: run the four-lens sweep silently after every major task completion —
flag only what fires, one line each. Session Pulse is enabled: 2-line effort split after
major milestones, logged in Handoff.MD updates.
Commit a git checkpoint at every working state and before any risky change
(consent.git_checkpoints = auto: commit + one-line announce).
Before starting a feature, build the smallest version that proves it works (per PRD.md's
"Done for v1"), checkpoint, then extend. Any architecture-shaping change gets a
plain-language delta proposal against the current diagram and user approval BEFORE code.
Log stack/architecture/behavior decisions as one line in Handoff.MD's Decisions; never
silently reverse a logged decision.

## Secrets (never commit, never print)
ANTHROPIC_API_KEY and DATABASE_URL live in Render env vars / local `.env` only.
User keys from Tab 4 are request-scoped, never persisted.
