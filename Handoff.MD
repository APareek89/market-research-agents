# Handoff — market-research-agents
last-synced: 001b41e

**Magic phrase:** `Refer to Handoff.MD in /Users/anandpareek/Documents/market-research-agents and begin`

## Previous session summary
2026-08-22: initial build + ship (see git log). Later session: backlog item 1 — server-side run persistence — built, QA'd locally, deployed.

## Current state
- ✅ Shipped: v1 live at https://agent-council.onrender.com (srv-da4jio49v7es738cps10, cold start ~1min) + server-side run persistence + Expert Mode lens retrieval (see git log & Learning.MD; QA in Loop.MD journal).
- Local dev: preview "mra" port 8620, "mra-2" port 8621 (config in BOTH repo and ~/Documents/.claude/launch.json — preview tool reads the latter). Env in .env (gitignored). KB re-ingest: `.venv/bin/python scripts/ingest_kb.py` (local + prod share ALS Supabase, so one ingest serves both).

## Pending points (user backlog, priority order)
- [ ] 2. Speed toggle "fast council": Vera+Cleo review draft in parallel, single combined revision (~35% faster).
- [ ] 3. Run Loop.MD golden set once to baseline quality (PAID — ask user first).
- [ ] 4. PPTX polish round 2 only if asked: content-aware slide splitting, charts from md tables.
- [ ] 5. Optional: cheap Haiku numeric-consistency pass before final output.
- [ ] Loop offer pending user answer (Loop.MD status: waiting_for_first_draft).

## Decisions
- 2026-08-22 — FastAPI + Python LangGraph + React(Vite) static, single Render service — canonical LangGraph; simplest deploy. (user approved)
- 2026-08-22 — GitHub acct APareek89; Render free plan — personal projects account; cost.
- 2026-08-22 — Flow: A0→A1→(A2→A1 refine)?→(A3→A1 final)? per toggles; one round each. (user approved)
- 2026-08-22 — Prompts/keys/toggles live in browser localStorage, sent per request — instant prompt effect, no key persistence, no auth needed.
- 2026-08-22 — Conversational memory in ALS Supabase Postgres, `mra_` tables, in-memory fallback — never hard-fail on DB.
- 2026-08-22 — Default model claude-opus-5 (per claude-api skill); dropdown incl. sonnet-5, haiku-4-5, GPT (BYO key).
- 2026-08-22 — Frontend dist/ committed to repo — Render python env has no node build step.
- 2026-08-22 — Multi-thread chat: per-conversation state (chats/runs maps keyed by conv id, tmp-key migration on conversation/plan event), concurrent runs supported, per-thread Stop. Chat renders mermaid (lazy chunk, dark theme) + styled tables; exports = branded PDF/PPTX w/ rasterized diagrams (XMLSerializer! see Learning.MD).
- 2026-08-22 — "Configure with AI" per agent (/api/synthesize-prompt). HF provider (router.huggingface.co BYO token). Revise passes capped at 3 tool iters.
- 2026-08-22 — Graph rebuilt DYNAMIC (build_stages per request): ordered review stages; custom agents (≤3) as reviewer/transformer; per-agent model select (agent > global pin > auto role default: haiku intake / sonnet analyst / opus reviewers).
- 2026-08-22 — Vera = Assess→Diagnose→Augment framework review; Cleo = 10-category client reviewer; PROMPTS_VERSION gate (v2) force-refreshes cached prompts on bump.
- 2026-08-22 — Server-side run persistence (user-specified arch): detached asyncio run tasks outlive requests; events → registry + mra_runs Postgres (best-effort); SSE viewers = tails w/ replay cursor + 15s heartbeat; client disconnect ≠ stop; Stop is explicit endpoint; startup marks orphaned 'running' rows error. Single-process registry — fine on Render single worker.
- 2026-08-22 — Hygiene round: chips → "Vera (Expert)" / "Cleo (Customer)"; ↻ Retry button on failed runs (payload kept per-conv in a ref — session-scoped, gone on reload, no duplicate user bubble on retry); FORMAT CONTRACT chain for output bloat (Scout brief §5 quotes user's format ask VERBATIM → Astra contract block + wraps deliverable in ===DELIVERABLE=== markers when contract exists → graph.py _extract_deliverable strips everything outside DETERMINISTICALLY on draft+revise → revise node now sees the original ask; all 4 reviewer prompts told the contract is binding). PROMPTS_VERSION 4 (wipes cached prompt edits by design). Exports: bundled DejaVu fonts (app/assets/fonts — unicode ₹/→/… everywhere incl. Render), [source: url] → [n] + linked Sources section (PDF) / Sources slide (PPT), typography polish, PPT tables get their own slide region (fixes text-overlap). QA: user's SEO ask 322→120 words, exactly 5 items ≤24w.
- 2026-08-22 — Expert Mode lens retrieval (per kb/RETRIEVAL_PIPELINE_SPEC.md, followed exactly): mra_frameworks mirrors kb/frameworks/ (20 rows, ingest_kb.py; vector(1024) col unused until >50); lens_prep node parallel w/ draft, gated on enabled&&expert_mode (reviewer/client ONLY, never custom); haiku router (json_schema; needs top-level `title` in schema — langchain quirk) + one sonnet composer → blind interrogation plan ≤9q/≤5q, [via X] tags; server enforces EXPERT_AGENTS prompt in build_stages (client prompt ignored; verified w/ marker-prompt E2E); UI: ★ toggle + banner + read-only prompt, user's own prompt preserved under it; ALL failures degrade silently to no-plan (DB-down E2E ✓). KB frontmatter is not strict YAML — kb.py uses a tolerant line parser; never "fix" the KB files.

## Session efficiency
🎯 ~80% feature · 🔧 ~15% support (browser click coordinate-space + second dev-server port for concurrent session) · 🔁 ~5% rework
