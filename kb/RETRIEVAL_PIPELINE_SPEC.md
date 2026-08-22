# Retrieval Pipeline Spec — dynamic lens selection for the review stages

Design contract for wiring the framework KB (kb/frameworks/) into the council. Written 2026-08-22;
implement in a separate coding session. Concept: the reviewer's interrogation lens is COMPOSED AT
RUNTIME — persona (user-authored) × lens (retrieved per task) — and prepared BLIND, in parallel
with the analyst's drafting, so questions derive from the problem, not the draft's frame.

## 1. Storage — Supabase (ALS prod; SAME database as the app's DATABASE_URL)

```sql
CREATE TABLE IF NOT EXISTS mra_frameworks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    cluster TEXT NOT NULL,
    origin TEXT,
    strength TEXT,
    when_to_use TEXT NOT NULL,          -- router surface
    trigger_signals TEXT[] DEFAULT '{}', -- router surface
    reviewer TEXT[] NOT NULL,            -- {vera}, {cleo}, or both
    pairs_well_with TEXT[] DEFAULT '{}',
    failure_modes TEXT[] DEFAULT '{}',
    body_md TEXT NOT NULL,               -- full markdown body (essence/questions/apply/contract)
    embedding vector(1024),              -- NULLABLE; unused until library >50 (see §3)
    updated_at TIMESTAMPTZ DEFAULT now()
);
```
- `CREATE EXTENSION IF NOT EXISTS vector;` guarded in try/except — embeddings NOT required for v1.
- Ingestion: `scripts/ingest_kb.py` — parse each kb/frameworks/*.md (YAML frontmatter + body),
  UPSERT by id. Idempotent; run manually and on deploy if cheap. INDEX.md/README.md are skipped.

## 2. Retrieval — LLM router, not embeddings (at this scale)

With ~20 frameworks, selection beats similarity search. Router = one claude-haiku-4-5 call:
- INPUT: the compact index (id, when_to_use, trigger_signals for rows matching the enabled
  reviewer) + the user's ask + the intake brief.
- OUTPUT (json_schema-constrained): `{lenses: [{id, why, weight: primary|secondary}], no_fit: bool}`
  — max 3 for Vera, max 2 for Cleo.
- FALLBACKS (never block the run): router error, DB unreachable, or no_fit →
  Vera: [assess-diagnose-augment]; Cleo: [working-backwards-prfaq]. Stage prompts already embed
  these two, so zero-lens degradation = current behavior exactly.
- pgvector path: only when the library exceeds ~50 (user uploads). Embed `when_to_use + trigger_signals`
  ONLY (never the body); retrieve whole rows. Column already exists; leave a TODO, do not build now.

## 3. Graph wiring — parallel blind prep

Current: intake → analyst → [stages]. New (only when reviewer and/or client stage enabled):

```
intake ──→ analyst ──────────────┐
   └─────→ lens_prep (parallel) ─┴→ stage1 → revise → … 
```
- LangGraph: add_edge(intake→analyst), add_edge(intake→lens_prep), then both edges into the first
  stage node (join). lens_prep writes `state.lens_plan`; analyst writes `state.analysis` — no key conflict.
- `lens_prep` node: router call → fetch selected rows → COMPOSE the interrogation plan per enabled
  reviewer: contextualize each framework's Interrogation set to this brief, dedupe overlaps,
  cap TOTAL at 9 questions for Vera / 5 for Cleo, each tagged `[via {framework name}]`.
  Model: claude-haiku-4-5 for routing; claude-sonnet-5 for contextualization (one call).
- Stage node change: if `state.lens_plan[stage]` exists, append to the stage's user content:
  "TASK-SPECIFIC INTERROGATION PLAN (prepared blind from the brief, before the draft existed).
   Apply it two-phase: (1) which questions does the draft answer / dodge / never consider;
   (2) fold the material misses into your findings. Cite the lens tag on each question you use."
- Custom agents: NO lens injection (their prompt is fully user-authored).
- Latency: lens_prep ≈ 5-15s, fully hidden under the analyst's 2-4 min draft. Free.

## 3.5 Expert Mode (the gate for retrieval)

Retrieval is NOT wired to the plain enable toggles — it is gated by a new per-agent **Expert Mode**
flag on the two review agents (reviewer + client only; never custom agents).

- Config from client: `agents.reviewer.expert_mode: bool`, `agents.client.expert_mode: bool`.
- `lens_prep` runs ONLY for agents with `enabled && expert_mode`. Neither in expert mode → no
  router call at all (today's behavior, zero added cost).
- **Expert prompt, server-enforced**: add `EXPERT_AGENTS` to `prompts.py` — a new default system
  prompt variant named "Expert" for each of reviewer and client. Author them from the current
  Vera/Cleo prompts, restructured around consuming the injected interrogation plan two-phase
  (answered / dodged / never-considered) with lens-tag citations. When `expert_mode` is true the
  SERVER ignores any client-supplied `system_prompt` for that agent and uses the Expert prompt —
  enforcement lives in `build_stages`, not just the UI.
- UI (Agents & Prompts): an "Expert Mode" toggle in the editor head for Vera and Cleo. When ON:
  the prompt textarea is read-only showing the Expert prompt, with a banner
  "★ Expert Mode — prompt is system-managed; task-specific framework lenses are retrieved and
  injected per run. Toggle off to edit your own prompt." Save / Discard / Configure-with-AI are
  disabled for the prompt (name + model stay editable). Chat toggle chip gains a ★ when expert.
- `/api/defaults` exposes the Expert prompts (read-only display) and `expert_mode` defaults (off).

## 4. Surface changes (small)

- SSE `plan` event: include a `lens_prep` node (label "Lens selection", agent "Router") so
  Chat progress + Observability show which frameworks fired; `node_complete.output` = chosen
  lenses + composed questions (this is gold for the Observability tab).
- No new tabs. Optional: chip row in the critique message footer listing fired lenses.
- `/api/defaults` may expose `frameworks_available: <count>` for a Settings-tab status line.

## 5. Non-negotiables

- NEVER block or fail a run on KB/DB/router problems — degrade to current behavior silently,
  log to server stdout.
- Question caps are hard caps (attention budget); materiality order, critical-first.
- `mra_` prefix for all new tables (shared ALS database).
- Keep `kb/` as the source of truth; DB is a mirror. Re-ingest overwrites DB, never the reverse.

## 6. QA checklist for the implementing session

1. Ingest → `select id from mra_frameworks` returns 20 rows.
2. Pricing ask ("what should X charge?") → router picks van-westendorp + unit-economics(+1); innovation
   ask → triz/scamper family; build-vs-buy ask → wardley. Spot-check 4-5 asks with Expert Mode on.
2b. Expert Mode gating: expert off (toggle on) → NO router call, user prompt honored; expert on →
   Expert prompt used even if the client sends a custom system_prompt (server-enforced); expert on
   for Vera only → Cleo gets no lens plan.
3. Vera's critique visibly cites lens tags and flags ≥1 "never considered" item.
4. DB paused/unreachable → run completes identically to today (no lens plan).
5. Both toggles off → lens_prep never runs (no wasted calls).
6. Latency: total run time within ±10% of pre-change baseline (prep hides under draft).
