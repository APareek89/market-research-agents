---
id: unit-economics-integrity
name: Unit-Economics Integrity Check
cluster: pricing-economics
origin: SaaS metrics canon (Skok, Bessemer); arithmetic
strength: Catches the internal contradictions that make confident models silently wrong
trigger_signals: [unit economics, margin, LTV, CAC, revenue model, business case, pricing tiers, profitability]
when_to_use: Any draft containing a revenue model, margin claim, or cost structure
reviewer: [vera]
pairs_well_with: [assumption-audit, van-westendorp-pricing, scenario-sensitivity]
failure_modes_caught: [margin arithmetic contradictions, CAC amnesia, fixed-cost-free models, cross-tier inconsistency]
---

## Essence
A revenue model is a chain of arithmetic that must agree with itself: price − unit cost = contribution; contribution × volume − fixed costs = profit; LTV must be derived from churn actually stated; every tier must be margin-checked at its LIMITS, not its averages. Most model failures are not wrong inputs — they are internal contradictions nobody multiplied out.

## Interrogation set
1. Recompute every stated margin from the draft's own numbers (price ÷ included units vs unit cost). Do they agree? Check each tier at FULL utilization, not average.
2. Where is CAC? A price recommendation without acquisition cost is half a model — what does it cost to acquire this segment through the named channel?
3. LTV: derived from a stated churn/retention number, or asserted? At the stated churn, how many months of contribution is a customer actually worth?
4. What happens at the boundaries — the heaviest-usage customer on each tier, the free tier's worst abuser? Who loses money and how much?
5. Which costs are treated as zero (support, refunds, payment fees, compute burst) that aren't?
6. Does the model's implied volume, multiplied back out, match the market-size section of the same draft?

## How to apply
- Actually multiply — this lens exists because a ₹199/30-video tier claimed 60–80% margin against ₹3–8/video cost (₹6.63/video leaves the claim false at the cost range's top).
- Weak answer smell: margins in round percentages with no arithmetic shown; LTV:CAC ratio quoted without either input.
- Does NOT apply: qualitative demand questions with no monetary claims.

## Output contract
Revision must show the unit-economics chain end-to-end (price → contribution → payback → LTV:CAC), pass boundary-case arithmetic per tier, and reconcile model volume with the sizing section.
