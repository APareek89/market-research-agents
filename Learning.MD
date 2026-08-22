# Learning.MD — market-research-agents

Log of bugs, corrective feedback, and hard-won fixes. 5-whys format:
**Symptom** → Why-chain (drill to deepest why, typed code/design/process/knowledge-gap) → Action taken (+which why-level) → Preventive action for the class.

## 2026-08-22 — Mermaid SVG→PNG export produced blank/failed images
**Symptom:** client-side rasterization of mermaid SVGs for PDF/PPT export failed (`img.onerror`), silently dropping diagrams from exports.
**Why-chain:** Image couldn't load the SVG data URL → SVG string was invalid XML → it was serialized with `innerHTML`, which emits HTML-style (unclosed) tags for `foreignObject` label content → mermaid emitted `foreignObject` labels even with `flowchart.htmlLabels:false` configured → (deepest why, type: knowledge-gap) assumed the config guarantees pure-SVG labels; it doesn't for all label types in mermaid v11.
**Action (targeted why #2):** serialize with `XMLSerializer().serializeToString()` — well-formed XML regardless of label type; verified 370KB PNG from a real diagram.
**Preventive (class):** any DOM→data-URL SVG handling in this repo must go through `svgToPng()` in md.jsx — never hand-serialize SVG with innerHTML/outerHTML.

## 2026-08-22 — Both chat runs "silently" produced nothing (QA scare)
**Symptom:** two runs closed instantly with no output; looked like a multi-thread wiring bug.
**Why-chain:** server rejected both with ConfigError → provider was `hf` with no token → my own Settings-tab UI testing had saved `provider:'hf'` to localStorage → (deepest why, type: process) QA left state behind in the shared browser profile.
**Action:** none needed in code (the error UI actually showed it — I looked at the wrong element first).
**Preventive (class):** after testing Settings/provider flows, reset `mra_settings` before the next test; when a run yields nothing, check `.error-box` contents FIRST.
