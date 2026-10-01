# Learning.MD — market-research-agents

Log of bugs, corrective feedback, and hard-won fixes. 5-whys format:
**Symptom** → Why-chain (drill to deepest why, typed code/design/process/knowledge-gap) → Action taken (+which why-level) → Preventive action for the class.

## 2026-08-22 — Mermaid SVG→PNG export produced blank/failed images
**Symptom:** client-side rasterization of mermaid SVGs for PDF/PPT export failed (`img.onerror`), silently dropping diagrams from exports.
**Why-chain:** Image couldn't load the SVG data URL → SVG string was invalid XML → it was serialized with `innerHTML`, which emits HTML-style (unclosed) tags for `foreignObject` label content → mermaid emitted `foreignObject` labels even with `flowchart.htmlLabels:false` configured → (deepest why, type: knowledge-gap) assumed the config guarantees pure-SVG labels; it doesn't for all label types in mermaid v11.
**Action (targeted why #2):** serialize with `XMLSerializer().serializeToString()` — well-formed XML regardless of label type; verified 370KB PNG from a real diagram.
**Preventive (class):** any DOM→data-URL SVG handling in this repo must go through `svgToPng()` in md.jsx — never hand-serialize SVG with innerHTML/outerHTML.

## 2026-08-22 — Claude chat couldn't read the prod URL (Render robots injection)
**Symptom:** pasting agent-council.onrender.com into claude.ai chat yielded nothing readable.
**Why-chain:** AI fetchers respect robots.txt → prod served `User-agent: * / Disallow: /` → the app never defined a robots.txt → (deepest why, type: knowledge-gap) Render free-tier `.onrender.com` subdomains INJECT a Disallow-all robots.txt at the edge whenever the app doesn't serve its own (anti-SEO-spam default).
**Action (targeted why #2):** app now serves /robots.txt (Allow all + explicit Claude-User/ClaudeBot/anthropic-ai), /llms.txt, and a readable static shell in index.html (SPA root was an empty div to non-JS readers). Verified via WebFetch: page now summarizable.
**Preventive (class):** any future Render-hosted app that should be AI/crawler-readable must serve its own robots.txt — the platform default silently blocks everything; SPAs additionally need static fallback content in the shell.

## 2026-08-22 — Fire-and-forget cleanup task could be GC'd (caught pre-commit)
**Symptom:** none yet — light FMEA on the run-persistence diff flagged that `asyncio.create_task(_finish_stopped(...))` kept no reference, so Python may garbage-collect the pending task and silently skip the stop-cleanup (run stuck 'running', UI hangs until reload).
**Why-chain:** cleanup runs in a fresh task because the cancelled task can't safely await → fresh task was unreferenced → (deepest why, type: knowledge-gap) asyncio only weakly references scheduled tasks; fire-and-forget is never safe.
**Action (targeted why #2):** store the task on the run object (`run.cleanup_task`), which the RUNS registry keeps alive.
**Preventive (class):** every `asyncio.create_task` in this repo must assign the result somewhere long-lived — grep for bare `create_task(` in review.

## 2026-08-22 — Both chat runs "silently" produced nothing (QA scare)
**Symptom:** two runs closed instantly with no output; looked like a multi-thread wiring bug.
**Why-chain:** server rejected both with ConfigError → provider was `hf` with no token → my own Settings-tab UI testing had saved `provider:'hf'` to localStorage → (deepest why, type: process) QA left state behind in the shared browser profile.
**Action:** none needed in code (the error UI actually showed it — I looked at the wrong element first).
**Preventive (class):** after testing Settings/provider flows, reset `mra_settings` before the next test; when a run yields nothing, check `.error-box` contents FIRST.


## 2026-09-30 — Cross-account late-response race
**Symptom:** code review found that an old account's401, completed JSON body, export Blob or continuing SSE reader could finish after a newer account was selected.
**Why-chain:** fetch completion does not coincide with body completion → a guard at headers alone is insufficient → fresh generation captured after an await can mislabel an old response → (deepest why, design) asynchronous work needs an immutable initiating account generation.
**Action:** capture before each request, check after JSON/Blob parsing and each stream read; cancel/release readers and abort viewers on account unmount. A current-session401 still expires the session, while a delayed old401 is discarded.
**Preventive:** deterministic tests exercise delayed401, JSON, Blob and SSE with A→B transitions, including returning toA and refreshing the same owner.

## 2026-09-30 — Legacy browser key persistence
**Symptom:** the original settings object included the API key in unscoped localStorage despite earlier docs saying keys were request-only.
**Why-chain:** all settings were serialized together → secret and preference lifetimes were treated equally → (deepest why, design) account identity and sensitive ephemeral state were absent.
**Action:** remove legacy unscoped preferences; persist only provider/model under an owner key. BYOK starts blank and clears on provider change, signout or reload. Remounting the account workspace clears file drafts and run-viewer state.
**Preventive:** inspect serialized values separately from rendered settings; server runs strip keys before persistence.

## 2026-09-30 — Honest free examples
**Symptom:** README had no starter transcripts and the original app had no mock mode; a normal six-stage council would spend tokens during a casual demo.
**Why-chain:** demo and live research shared one provider path → (deepest why, design) no server-owned prepared execution context.
**Action:** three authored illustrative replies now use the normal graph with explicit cached provenance. UI labels the examples and warns that new questions use the selected provider. A caller cannot convert arbitrary input into a cached run.
**Preventive:** fixture checks validate both no-provider execution and preserved normal routing; do not describe authored examples as current research.


## 2026-10-01 — Saved trace invisible after reload
**Symptom:** root browser QA found a saved prepared report survived refresh, but Observability showed no runs.
**Why-chain:** history returned the assistant message's trace → Chat restored it only into its message map → Observability read a separate live-event list → (deepest why, design) the two views had no restoration contract.
**Action:** restore exact saved traces into Observability with stable conversation/message IDs, original timestamps and cached metadata. Preserve active/error runs and deduplicate completed entries; do not infer completion status or total duration from partial traces.
**Preventive:** tests cover idempotent history loading, multiple messages, cached labels, partial/absent traces and active-run preservation.


## 2026-10-01 — Revoked SSE session left the workspace open
**Symptom:** independent integration review found that server revocation stopped the SSE viewer, but its `session_expired` frame did not clear the client account.
**Why-chain:** only HTTP401 triggered client expiry → SSE already had successful headers → the event passed through handlers without a matching case → (deepest why, design) transport-level and event-level authentication failures used different lifecycles.
**Action:** central SSE parsing expires only the initiating current generation and throws outside the malformed-frame catch; finally cancels and releases the reader.
**Preventive:** a deterministic test delivers expiry followed by private data in the same chunk, then repeats after A→B. Current expiry clears the session, stale expiry preserves B, and neither delivers the following frame.


## 2026-10-01 — Temporary proof guard double-decoded provider gzip
**Symptom:** the first controlled dispatch returned HTTP200 with billed usage, but the guard failed before a final report was persisted.
**Why-chain:** `aiter_bytes()` had already decompressed the response → reconstruction retained `Content-Encoding: gzip` → the new response attempted a second decode → (deepest why, protocol handling) decoded body bytes were combined with wire-encoding metadata.
**Action:** only the external operator guard changed: save the bounded decoded body privately, strip encoding/old length/transfer headers, retain safe request metadata, then reconstruct. The installed SDK and ordinary graph passed a compressed fixture before a separately authorized retry. No application source changed.
**Preventive:** test the whole installed SDK path with compressed transport and persistent exclusive dispatch claims; retain failed attempts and their real usage instead of erasing them. Two dispatches cost an estimated $0.0034410; only the corrected attempt completed a report. Its unsupported Basic-multipack assumption remains a factual-quality limitation.
