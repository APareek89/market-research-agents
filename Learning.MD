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
