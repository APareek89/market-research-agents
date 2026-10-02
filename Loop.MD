# Loop.MD
status: on — free launch verification only

Current 2 October FMEA candidate: use `docs/qa/2026-10-02/report.md` for exact free-check counts and remaining release gates. No new paid authorization is inferred; local previews are9002 (GetCited) and9004 (Market Research).
**Goal:** preserve the complete council workflow while proving authenticated tenant isolation, bounded resource use, cached examples and a usable shared UI. This launch authorizes free checks after meaningful changes; it does not authorize repeated paid evaluations.

## Current launch checks
- Baseline:35 HTTP assertions passed with real graph/routing, extraction, history/replay, both toggle combinations, a custom stage, prompt override, explicit stop, errors and PDF/PPTX. All provider models were fixtures, with non-loopback sockets/DNS denied.
- Independent baseline browser: six-stage council, report, Scout expansion, Observability and reload/history passed with no console errors.
- Client:13 deterministic tests pass for CSRF/multipart, delayed old401, current401, same-owner refresh, identity return, auth errors, late SSE/JSON/Blob and explicit local fixture mutations; three of these cover persisted trace restoration, idempotence and partial history.
- Vite production build passes; Mermaid retains an existing large-chunk warning. Source and committed dist are rebuilt together.
- Integrated real PostgreSQL auth/mock preview is running on 8953; root browser checks passed on 1 October;36 unique backend contracts also passed in isolated PostgreSQL/mock environments. Hosted free tests and the corrected limited paid flow passed; independent paid SQL/hash audit passed; ordinary-runtime restoration and final browser smoke passed.

## Free commands
```bash
(cd frontend && npm test && npm run build)
.venv/bin/python -m compileall -q app
```
Backend fixture tests use isolated data and model mocks. Do not send a normal `/api/chat` request in live mode and label it a free test: even both review stages disabled normally invokes Scout and Astra.

## Release status
- Completed: independent SQL/ledger audit, first-attempt reconciliation and matching durable report/trace/SSE/provider-deliverable hashes.
- Completed: ordinary live mode without temporary proof command/mounts, followed by the root’s free smoke.
- Final exact docs/source inventory, redacted history/current-tree/index scans and reviewed source publication.
- Root approval before staging/commit/push; no automatic checkpoints.

## Historical golden set (paid — not part of automatic launch checks)
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

- 2026-09-30 — FREE launch baseline and9 client regressions passed as detailed above. No provider dispatch has been made by the UI workstream. Those acceptance checks were pending at that checkpoint.

- 2026-10-01 — FREE root browser confirmed session/report persistence across overnight reload, both themes, 390px layout and PDF/PPTX completion with no errors. Saved-trace visibility and the OpenAI/HF model-control label were corrected;12 client tests and fresh production build pass. Focused root browser retest passed: saved six-stage cached trace, Scout expansion, effective global model control, both themes / 390px and signout.

- 2026-10-01 — FREE documented fixture mode verified in a cleared process with all socket connects/DNS denied: health200, authoff, no configured key,3 examples and6 cached trace steps. No provider requests.

- 2026-10-01 — Final client expiry regression passed: current-generation `session_expired` closes the session and reader before any following private frame; a stale A expiry leaves B signed in.13 frontend tests total, production build passes.
- 2026-10-01 — Backend:36 unique contracts pass (35 in the unified suite plus the additional legacy-schema test). Subsequent targeted DB/trace and HTTP upload checks repeat existing coverage and are not counted again. Coverage includes real PostgreSQL accounts/revocation/CSRF/ownership, actual SDK transport mocks, graph/custom/stop behavior, safe-network limits, immutable upload contracts and valid PDF/PPTX parsing. No provider calls. Run `.venv/bin/python -m unittest discover -s tests -v` only with the documented isolated test environment; the fixture harness owns its database lifecycle.

- 2026-10-01 — First controlled PAID core attempt did **not** complete the report. One OpenAI response returned HTTP200 with 858 input tokens and 499 output tokens (384 reasoning,0 cached); estimated provider usage cost USD0.0012125, not an invoice. The temporary operator proof guard then failed reconstructing an already-decoded compressed response, before the live analysis stage completed. The application correctly retained an uncertain conservative reservation USD0.006126. Failed attempt claims, error run and independent evidence are preserved; no automatic retry occurred. At that point, paid core acceptance remained pending a separately reviewed correction. The ordinary app source was unchanged.

- 2026-10-01 — LIVE FREE checks passed on unchanged image `c089e8e8463d4534`: two-account ownership, six cached stages/replay, exact 89-byte S3 version/hash and anonymous 403, readable PDF/PPTX, revoked session, prior rows preserved, TLS 1.3 and no usage delta. Root live browser passed the prepared pricing example, restored trace, themes,390px and account flow.
- 2026-10-01 — Corrected PAID attempt completed after the response guard was fixed and independently checked with the installed SDK and compressed fixture. One GPT-5-mini dispatch used 858 input/1007 output tokens (896 reasoning included,0 cached); estimated USD0.0022285. First failed attempt was reconciled to its recorded estimated USD0.0012125 without rewriting its error run. Total 2 actual dispatches, estimated USD0.0034410, one completed report; no automatic retry. App image/source unchanged.
- Proof limit: Scout was prepared and reviewers were off; the live analyst recommended Growth at$0.15/image but assumed four Basic plans could be purchased. This is a bounded core execution proof, not a fully paid council, web-research or factual-quality certification. Independent paid SQL/hash audit passed; ordinary-live restoration and final browser smoke passed.

- 2026-10-01 — Final ordinary-live gates passed on exact `c089e8e8463d4534`: healthy, non-root, read-only root, auth enabled, mock disabled, TLS 1.3, awslogs, prior services unchanged. Corrected proof evidence remains sealed. Root reopened the saved actual report/trace and ran a new free watermark example; console errors/warnings were empty. No additional paid call was made for this smoke.
