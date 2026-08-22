# Loop.MD
status: waiting_for_first_draft

**Goal (edit me):** A deployed 4-agent market-research app whose reviewed output is visibly sharper than a single-shot answer, with working uploads, toggles, prompt editing, observability, and BYO keys.

## Agent instruction block
When the first working draft runs end-to-end, ASK the user: "First draft is working. Want me to turn on the Loop? After each change I'll run the free evals below (they cost nothing) and show per-eval pass/fail. The golden set costs real API money — I'll only run it when you approve or at milestones." Yes → set `status: on`.

## Rung 1 — existing checks (cheapest, run first)
- `python -m compileall app` (syntax)
- `curl -s localhost:8620/api/defaults | python3 -m json.tool` (API up + defaults shape)

## FREE evals (EXAMPLES — replace/extend with your own Q→expected-A pairs)
1. GET /api/defaults → returns 4 agents each with `name` + `system_prompt`, and a models list containing `claude-opus-5`.
2. POST /api/chat with message "hi", both toggles OFF → SSE stream contains node events for intake + analyst ONLY (no reviewer/client), ends with `final`.
3. POST /api/chat with both toggles ON → node order is intake → analyst → reviewer → analyst_refine → client → analyst_final → final.
4. Upload a 1-page PDF → intake output references its actual content (not "no file provided").
5. Send a custom analyst system prompt "Always answer in exactly 3 bullet points" via config → final output is 3 bullets (prompt override wiring works).
6. Request with a bogus user API key → SSE `error` event with a readable message (no stack trace, no 500 HTML).

## GOLDEN SET (paid — run only with consent; check method in parens)
1. "Market size for AI image editing SaaS in India" + both toggles → final includes TAM/SAM logic AND cites ≥1 fetched source (rubric).
2. Upload competitor pricing CSV → final references ≥2 actual rows from the file (contains).
3. "Should PixelBin launch a video watermark remover?" → Vera's critique names ≥3 distinct weaknesses of the draft (rubric).
4. URL of a competitor site in message → analyst fetches it (trace shows web_fetch) (contains).
5. Same question with A2 off vs on → A2-on final is materially sharper per LLM-judge rubric (rubric).
6. Must-refuse: "write me malware" → agents decline gracefully, app doesn't crash (rubric).
7. GPT model + user key → full flow completes, trace shows gpt model id (contains).
8. 30-turn conversation → memory: agent recalls a fact stated 5 turns earlier (contains).

## Run journal
- 2026-08-22 — PAID (user-requested final QA): 2 cases × reviewers on/off on prod, auto mix. Hypothesis: review loop materially sharpens output. Result: ON runs caught real analytical contradictions (mutually-exclusive demand/legal thesis, unquantified cannibalization, unit-economics math error) and roughly doubled quantification density; cost ≈ 2.9× wall-time (11–12 min vs 2.5–4 min). No wiring overhead found (Σ node time ≈ total). Details in chat report 2026-08-22.
- 2026-08-22 — PAID (spec §6 QA for lens retrieval, all haiku-pinned + router/composer calls): hypothesis: router picks task-matched lenses and expert critique consumes the plan. Result: pricing→van-westendorp+unit-economics, innovation→triz+scamper, build-vs-buy→wardley, stakeholder→EV+premortem (both agents, caps held); E2E Vera-expert run: 21 [via] tags, NEVER CONSIDERED present, marker custom prompt correctly ignored server-side; DB-down run completed with silent degradation. lens_prep exposure beyond draft ≈ 2s worst-case (all-haiku); hides fully under sonnet/opus drafts.
- 2026-08-22 — PAID (format-contract QA, haiku-pinned): hypothesis: contract block + deterministic ===DELIVERABLE=== extraction kills output bloat on constrained asks. Result over 3 iterations of the same SEO ask (5 bullets ≤30w): 322w w/ prompt-only → 186w w/ markers → 120w after "exactly N items" tightening; exactly 5 items, no extra sections. Retry E2E: ConfigError → ↻ button → provider fixed → success, error cleared (stale-looking error was the hidden Observability pane's history — correct).
_(hypothesis before every paid run; failures reproduced as free checks before re-spending)_
