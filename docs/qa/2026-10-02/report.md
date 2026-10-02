# Market Research Agents — free FMEA and regression review, 2 October 2026

The matrix covers **111 distinct possible failure scenarios across all 12 Power Coding categories**. It does not claim that many bugs: 13 scenario rows are addressed by 6 grouped corrective changes. Existing controls, residual risks, product limits, historical limits and unverified cases are identified separately.

Baseline commit: `f7e7ebec378d33168b9b49ab65f0d1a88209aeae`. Root deployed the reviewed image; see `aws-release.json`. The worker made no real provider calls or live-data writes and did not operate a deployment.

## Corrective changes

- Boolean review/expert/enabled settings now require actual booleans, and custom stage modes are allowlisted. Strings such as false cannot accidentally enable paid stages.
- The metered model wrapper validates explicit terminal status after settlement. Truncation, refusal, missing finish status, invalid tool requests, empty tool-call completions and whitespace-only answers fail before report/tool execution. Empty extracted deliverables also fail before assistant persistence or final success.
- Provider exceptions record bounded provider/model/run/status/category metadata without raw error text, request content, keys or stack traces.
- Stored preferences are shape-validated before React receives them; saved key values are discarded. Unavailable browser storage is treated as optional, avoiding a workspace crash.
- A failed Stop request now displays its safe error instead of silently disappearing.
- Mobile report tables preserve readable column widths and scroll within the report, so short plan names are not split into narrow fragments.

## Evidence and scoring

The `repository_category` column additionally maps all scenarios to the repository’s twelve configured category names; all twelve are represented. The main category column follows the shared portfolio FMEA checklist.

Statuses: `controlled` 89, `fixed` 13, `product_limit` 6, `historical_limit` 1, `unverified` 2.

Evidence kinds: `source_inspection` 49, `automated` 56, `scenario_simulation` 3, `not_run` 3.

[fmea.csv](fmea.csv) and [fmea.json](fmea.json) contain each scenario, source/test reference, effect/control, S/O/D, RPN and priority. Scores are product-aware ordinal judgments, not measured probabilities. For fixed rows the score describes the pre-fix risk; for other rows it describes current controls or the remaining evidence gap. RPN=S×O×D; P0≥200, P1≥100, P2<100. All pre-fix P0 rows have corrective code and executed regressions; source-inspected cases are not labelled tested.

Validation: 37 offline backend tests, 5 normal auth http test groups, 16 frontend node tests. Counts represent different test scopes and must not be added to claim unique user scenarios. Production build passed; Vite retains its existing large-chunk warning.

Checks use real code with local PostgreSQL, normal account flows and intercepted/fixture provider transports. Non-loopback network access is denied in the server/SDK fixture runners. No configured provider credentials are loaded. A model-authored/session-authored response is marked as a simulation, never provider acceptance. Safe HTTP receipts and a validation inventory are saved alongside this report.

Root checked the normal-auth report and Observability stage chain. The final mobile recheck at 390px confirms document width390px, readable98px table cells with Basic/Growth/Team intact, and horizontal scrolling contained inside the report. See `browser-qa.json` for the screenshot hash and exact scope. This is local fixture UI acceptance, not hosted or provider acceptance.

## Remaining limits

- The six-stage pricing council used responses independently authored by the parent session from actual system prompts, wrapped through the installed SDK and real graph/PostgreSQL path. It is not six real provider responses or a quality benchmark.
- The earlier live analyst report assumed repeat purchases of Basic plans. That historical limitation remains; the new synthetic final explicitly states that repeat purchase permission is unconfirmed.
- Unpriced BYOK usage can have unknown dollar cost. A single server worker is required because active-run capacity is local; this is not a distributed scheduler.
- Expert-lens fallback, hosted load, current external research and actual provider answer quality remain outside completed acceptance. This worker has not deployed the candidate.

## Release gates

The parent must review the exact diff, package/build the exact Linux image, preserve live environment/mounts, smoke it without network, and perform the approved release plus normal-account readback. No paid quality, current-law or load claim is implied by a green fixture.

## Root release verification

Root activated image `2a4d5450b211` on 2 October 2026 using an image-only update. Authentication remains enabled and mock mode disabled. Environment, mounts, runtime bounds and other apps were preserved; the release operator made zero provider calls. `aws-release.json` records exact image/source hashes. This proves deployment, not a new paid model-quality check.
