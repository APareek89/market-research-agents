# Prompt for the implementing session (copy-paste below the line)

---

Refer to Handoff.MD in /Users/anandpareek/Documents/market-research-agents and begin. Then implement the **dynamic lens-retrieval pipeline** for the review agents.

**Read first, in order:** (1) `kb/RETRIEVAL_PIPELINE_SPEC.md` — the full design contract, follow it exactly; (2) `kb/frameworks/README.md` — the KB file schema; (3) `kb/frameworks/INDEX.md` — the 20 frameworks. The KB content is final — do not edit framework files, only ingest them.

**What to build:**
1. **Storage**: `mra_frameworks` table in the app's existing Postgres (the `DATABASE_URL` already in `.env` / Render env — this IS the Agentic Learning Studio prod Supabase; keep the `mra_` prefix, never touch non-`mra_` tables). Ingestion script `scripts/ingest_kb.py` parsing frontmatter+body from `kb/frameworks/*.md`, idempotent upsert by id. Run it once and verify 20 rows.
2. **Retrieval**: LLM router (claude-haiku-4-5, json_schema output) over the compact index — NOT embeddings at this scale; the spec's §2 has the exact contract, caps (max 3 lenses Vera / 2 Cleo) and fallback rules. The nullable `embedding vector(1024)` column ships unused (future >50-framework path).
3. **Pipeline**: new `lens_prep` node running IN PARALLEL with the analyst draft (fires only when Agent 2 and/or Agent 3 toggles are enabled — never for custom agents, never when both are off). It composes a blind, task-contextualized interrogation plan per enabled reviewer (≤9 questions Vera, ≤5 Cleo, each tagged `[via {framework}]`), which stage nodes append to Vera/Cleo's input with the two-phase apply instruction (answered / dodged / never-considered). Spec §3 has the graph wiring.
4. **Surfaces**: `lens_prep` appears as a node in the SSE plan + Observability trace with the chosen lenses as its output. Nothing else UI-wise.

**Non-negotiables (spec §5):** a KB/DB/router failure must NEVER block or degrade a run — silently fall back to today's behavior (Vera already embeds assess-diagnose-augment, Cleo embeds the stakeholder checklist). Hard question caps. `kb/` stays the source of truth; DB is a mirror.

**QA before pushing** (spec §6): ingest count = 20; router picks pricing lenses for a pricing ask / wardley for build-vs-buy (spot-check 4 asks, haiku-pinned); Vera's critique cites lens tags and flags ≥1 never-considered item; run with DB unreachable completes identically to today; toggles-off runs never call the router; total latency within ±10% of baseline (prep hides under the draft). Commit per the repo's power-coding rules (secret scan runs pre-commit) and push — Render auto-deploys; smoke-test prod with one both-toggles-on run and confirm the lens node appears in Observability.
