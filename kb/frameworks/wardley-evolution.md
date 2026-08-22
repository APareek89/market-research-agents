---
id: wardley-evolution
name: Wardley Evolution (Build–Buy–Commoditize Timing)
cluster: competition-moats
origin: Simon Wardley, Wardley Mapping (2005–)
strength: Times decisions against component evolution — what to build vs buy vs wait out
trigger_signals: [build vs buy, horizontal vs vertical, platform strategy, infrastructure decision, commoditization, timing]
when_to_use: Strategy drafts where WHAT to build depends on how fast underlying components commoditize
reviewer: [vera]
pairs_well_with: [seven-powers, porter-five-forces, disruption-theory]
failure_modes_caught: [building what will commoditize, differentiating on utilities, static landscape assumption]
---

## Essence
Every component in a value chain evolves: Genesis → Custom-built → Product → Commodity/Utility. Strategy errors are mostly TIMING errors — building custom what is becoming a utility (waste), or treating a still-genesis capability as reliable infrastructure (fragility). Map the user need, its component chain, and each component's evolution stage before choosing where to play.

## Interrogation set
1. Decompose the recommendation's value chain into components. For each: genesis, custom, product, or commodity — TODAY?
2. Which component is the draft proposing to BUILD that will be a commodity/utility within 24 months? (In AI: model routing, RAG plumbing, agent orchestration are racing down this curve.)
3. Which component does the thesis DEPEND on that is still genesis-stage — and what happens when it shifts or breaks?
4. Where is differentiation actually possible — only in components left of "product"; is the draft differentiating on a utility?
5. Who benefits from commoditizing each layer, and are they (a hyperscaler, a model lab) already doing it?
6. If the recommendation waited 12 months, which parts get cheaper/free? What is the true cost of building now?

## How to apply
- One-line evolution verdict per major component beats a full map; demand movement arrows, not a static list.
- Weak answer smell: "we'll build our own X" where X has three funded startups and an open-source standard; horizontal-infra recommendations with no answer to "why won't the model labs eat this layer?"
- Does NOT apply: pure demand/pricing questions with a settled product.

## Output contract
Revision must show the component chain with evolution stages, justify build-vs-buy per component against its 24-month trajectory, and place differentiation only on non-commodity components.
