# Handoff — market-research-agents
last-synced: cb9b40f

**Magic phrase:** `Refer to Handoff.MD in /Users/anandpareek/Documents/market-research-agents and begin`

## Previous session summary
Initial build session (2026-08-22): scaffolded whole app from user spec + power-coding setup.

## Current state
- ✅ SHIPPED v1: https://agent-council.onrender.com (Render free, srv-da4jio49v7es738cps10, Singapore; cold start ~1 min after idle). GitHub: APareek89/market-research-agents (main).
- ✅ QA passed local+prod: 4 tabs, full 6-node run, toggles-off path, prompt override, bad-key error, extraction unit tests, Postgres persistence (Supabase mra_ tables).
- Local dev: preview server "mra" on port 8620 (8600 is plotline-api). Env in .env (gitignored).

## Pending points
- [ ] Loop offer pending user answer (Loop.MD status: waiting_for_first_draft — first draft works).
- [ ] Golden-set paid evals never run (consent.paid_evals=ask).

## Decisions
- 2026-08-22 — FastAPI + Python LangGraph + React(Vite) static, single Render service — canonical LangGraph; simplest deploy. (user approved)
- 2026-08-22 — GitHub acct APareek89; Render free plan — personal projects account; cost.
- 2026-08-22 — Flow: A0→A1→(A2→A1 refine)?→(A3→A1 final)? per toggles; one round each. (user approved)
- 2026-08-22 — Prompts/keys/toggles live in browser localStorage, sent per request — instant prompt effect, no key persistence, no auth needed.
- 2026-08-22 — Conversational memory in ALS Supabase Postgres, `mra_` tables, in-memory fallback — never hard-fail on DB.
- 2026-08-22 — Default model claude-opus-5 (per claude-api skill); dropdown incl. sonnet-5, haiku-4-5, GPT (BYO key).
- 2026-08-22 — Frontend dist/ committed to repo — Render python env has no node build step.

## Session efficiency
(pending first milestone)
