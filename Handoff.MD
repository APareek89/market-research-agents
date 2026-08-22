# Handoff — market-research-agents
last-synced: (pre-first-commit)

**Magic phrase:** `Refer to Handoff.MD in /Users/anandpareek/Documents/market-research-agents and begin`

## Previous session summary
Initial build session (2026-08-22): scaffolded whole app from user spec + power-coding setup.

## Current state
- ✅ v1 built & local QA passed: all 4 tabs, full 6-node run (haiku), toggles-off path, prompt override, bad-key error path, extraction unit tests, Postgres persistence across reload (Supabase mra_ tables live).
- 🚧 Deploy: push to GitHub (APareek89) + Render (free), then smoke test.

## Pending points
- [ ] Deploy to Render, smoke test prod URL.
- [ ] Offer the Loop (Loop.MD status: waiting_for_first_draft) — first draft IS working; ask user next session if not answered.

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
