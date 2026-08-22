# Handoff — market-research-agents
last-synced: dbbbdd4

**Magic phrase:** `Refer to Handoff.MD in /Users/anandpareek/Documents/market-research-agents and begin`

## Previous session summary
Initial build session (2026-08-22): scaffolded whole app from user spec + power-coding setup.

## Current state
- ✅ SHIPPED v1: https://agent-council.onrender.com (Render free, srv-da4jio49v7es738cps10, Singapore; cold start ~1 min after idle). GitHub: APareek89/market-research-agents (main).
- ✅ QA passed local+prod: 4 tabs, full 6-node run, toggles-off path, prompt override, bad-key error, extraction unit tests, Postgres persistence (Supabase mra_ tables).
- Local dev: preview server "mra" on port 8620 (8600 is plotline-api). Env in .env (gitignored).

## Pending points
- [ ] Loop offer pending user answer (Loop.MD status: waiting_for_first_draft — first draft works).
- [x] 4-run comparative QA done 2026-08-22 (see Loop.MD journal).

## Decisions
- 2026-08-22 — FastAPI + Python LangGraph + React(Vite) static, single Render service — canonical LangGraph; simplest deploy. (user approved)
- 2026-08-22 — GitHub acct APareek89; Render free plan — personal projects account; cost.
- 2026-08-22 — Flow: A0→A1→(A2→A1 refine)?→(A3→A1 final)? per toggles; one round each. (user approved)
- 2026-08-22 — Prompts/keys/toggles live in browser localStorage, sent per request — instant prompt effect, no key persistence, no auth needed.
- 2026-08-22 — Conversational memory in ALS Supabase Postgres, `mra_` tables, in-memory fallback — never hard-fail on DB.
- 2026-08-22 — Default model claude-opus-5 (per claude-api skill); dropdown incl. sonnet-5, haiku-4-5, GPT (BYO key).
- 2026-08-22 — Frontend dist/ committed to repo — Render python env has no node build step.
- 2026-08-22 — "Configure with AI" per agent (modal: notes + doc upload → /api/synthesize-prompt writes new system prompt, user reviews+saves). HF provider (router.huggingface.co/v1 via ChatOpenAI, BYO hf_ token, preset list + free-text id). Latency fix: revise passes capped at 3 tool iters + search-only-if-demanded wording.
- 2026-08-22 — Graph rebuilt DYNAMIC (build_stages/build_council_graph per request): ordered review stages between draft & end; custom agents (≤3, browser-defined) as reviewer (feedback→revise) or transformer (replaces analysis) stages; stage_order from client, pipeline bar UI. Chat: sidebar convo list, Stop (AbortController), tabs stay mounted (state survives switch), PDF/PPT export via /api/export (fpdf2 latin-1 sanitize + python-pptx). Per-agent model select in Agents tab (precedence: agent > global pin > auto role default).
- 2026-08-22 — Per-agent "auto" model mix default (haiku intake / sonnet analyst / opus reviewer+client) for speed; Settings picker can pin one model for all agents. Prompts tab: explicit Save (drafts, unsaved indicators) + Reset to default. Fixed "Reading your files…" showing without files.
- 2026-08-22 — Vera (A2) rebuilt on user's Assess→Diagnose→Augment DOCX framework (contextualize-first, max 6 failure modes, gap/why/type/augment format); gets user's original ask + brief + draft. Cleo (A3) rebuilt as 10-category client reviewer (value prop, objective fit, structure, actionability, evidence, quantification, risk, clarity, hygiene, completeness). PROMPTS_VERSION gate (v2) force-refreshes cached browser prompts on bump — wipes user edits on upgrade, by design.

## Session efficiency
(pending first milestone)
