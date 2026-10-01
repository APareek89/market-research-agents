# Portfolio launch review

Review scope: current launch diff against the council PRD, with the original provider-free baseline preserved. Local browser acceptance passed on 1 October; 36 backend contracts passed; hosted free acceptance and the corrected limited paid flow passed; paid SQL/hash audit passed; ordinary-live restoration and final browser smoke passed.

## Client review — 2026-09-30

- **Account boundary, high impact:** a new owner remounts the entire workspace, clearing draft files, BYOK, prompt-editor drafts and run-viewer state. Persistent preferences use owner keys; old unscoped values are removed. Header theme is intentionally global. Server owner checks remain authoritative.
- **Delayed responses, high impact:** request-start generation is retained through headers, JSON bodies, export Blobs and SSE reads. Current-session401 signs out; old401 cannot expire a newer owner. Viewer controllers abort on unmount, and stream readers cancel/release. Ten focused session regressions pass, including A→B, A→out→A and same-owner refresh.
- **Provider cost, high impact:** example cards call only the dedicated immutable example endpoint; reports and trace metadata say prepared/no provider. The composer explicitly states that new messages use the selected provider. No model request runs on render, theme change or opening Settings. Configure with AI remains an explicit action.
- **Original workflow, medium impact:** the chat thread/run maps, temporary-to-real conversation migration, stage order, review/transformer semantics, stop endpoint and replay are retained. Tabs remain mounted during a run. The original35 baseline HTTP assertions covered these paths before authentication changes; merged backend acceptance is tracked separately.
- **Output safety and exports, medium impact:** DOMPurify remains before Markdown insertion; Mermaid uses strict mode. Theme rendering and export rendering share a serialized Mermaid queue. Export retains XMLSerializer SVG handling and checks account identity before and after asynchronous work. PDF/PPTX format checks passed in the baseline; root verified integrated PDF/PPTX button completion without console errors.
- **Usability, medium impact:** all new icon-only controls have names; file-removal and stage-move controls also have explicit names. Forms expose labels, busy states and readable failures. Semantic surfaces support both themes; mobile rules stack the sidebar and constrain tables to inner horizontal scrolling. Root verified both themes and 390px report layout; saved-trace and model-control retests also passed on 1 October.

## Known limits and required release gates

Email verification and password-recovery delivery are not configured. Preferences persist on the local device under account-scoped keys; this is not encrypted browser storage. Observability includes live runs and exact saved traces from opened history conversations; restored entries are labeled saved, preserve cached metadata and do not invent an elapsed total. A failed expert-lens preparation degrades to ordinary review. Search availability is not guaranteed, and authored examples are not current research. One worker owns running tasks; a restart marks unfinished work interrupted rather than resuming it.

Independent backend/infra review, merged tests, real-account A/B isolation, immutable-upload proof, browser acceptance, the bounded paid proof and ordinary-runtime restoration passed. Final source publication requires the exact reviewed index and clean redacted scans; this document itself does not authorize a commit.


## 2026-10-01 follow-up

Root browser review found that the original history loader fetched saved traces without displaying them in Observability. Saved message IDs now restore stable entries, preserve timestamps and exact cached steps, and replace redundant completed entries while retaining active/error runs. Three focused restoration tests pass in addition to the ten session tests. An older trace without a completion status is labeled saved, not newly completed. Per-agent model controls now remain editable for Claude only; OpenAI/HF display the effective global model and explain its source. No routing/provider behavior changed.

Root confirmed latest compiled UI after reload: six saved cached steps restored, Scout expandable, provider model correct, light/dark at 390px without overflow, both export buttons complete and signout clears the workspace. Final hosted gates passed and are recorded below. Frontend runtime is frozen.


The bounded independent server review found no additional material account-boundary or core-loop defect in auth/data/main/usage/export. Its one integration finding—ignored SSE session-expiry frames—was corrected centrally with a current/stale-generation regression and immediate reader cancellation. The final client suite contains 13 checks. Backend verification contains 36 unique checks, with repeat rechecks recorded separately. Hosted S3, live browser, controlled paid proof and ordinary-runtime receipts passed.


## Live verification and quality boundary — 2026-10-01

Live owner/session/S3/export checks passed with no provider usage, alongside the independent browser flow. The same application image then completed a bounded paid report after a temporary operator guard failed on decoded compressed-response headers. The first billed failure remains an error run; it was not erased or relabeled successful. Across both attempts there were two dispatches and estimated $0.0034410 usage.

The final answer contains a correct Growth/$0.15-per-image recommendation and an unsupported four-Basic-plans assumption. Prepared intake and disabled reviewers limit this proof to execution/persistence. It is not a fresh-research or factual-accuracy evaluation. Independent SQL evidence now verifies the 384-byte report and matching trace/SSE/provider-deliverable hashes. The temporary guard was removed; final ordinary-live infrastructure and browser checks passed.
