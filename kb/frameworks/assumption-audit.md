---
id: assumption-audit
name: Assumption Audit & Fermi Decomposition
cluster: reasoning-qa
origin: First-principles practice; Fermi estimation; Douglas Hubbard "How to Measure Anything"
strength: Separates load-bearing assumptions from facts and makes every number auditable
trigger_signals: [market sizing, forecast, revenue model, any quantified claim, unit economics]
when_to_use: Any draft whose conclusion rests on numbers or unstated premises
reviewer: [vera]
pairs_well_with: [tam-sam-som, unit-economics-integrity, scenario-sensitivity]
failure_modes_caught: [fact-assumption blending, unauditable numbers, arithmetic inconsistency, false precision]
---

## Essence
Every quantitative claim decomposes into facts (sourced), assumptions (chosen), and arithmetic (checkable). A draft is auditable only when the three are visibly separated. Fermi decomposition — rebuilding a number from first-principles drivers — is the fastest way to expose which assumption is doing the heavy lifting.

## Interrogation set
1. List the five most load-bearing numbers. For each: fact, assumption, or arithmetic? Where is the source or the reasoning?
2. Rebuild the headline number bottom-up from drivers (users × frequency × price…). Does it land within 2× of the draft's figure? If not, which driver diverges?
3. Which single assumption, moved to its plausible extreme, flips the recommendation? Is it flagged as such?
4. Do the numbers agree with EACH OTHER? (Check totals vs components, margins vs price minus cost, shares summing >100%.)
5. Where does precision exceed knowledge — "$3.42B by 2031" from a two-assumption chain?
6. What is asserted "from memory" that a 30-second search could source or falsify?

## How to apply
- Actually do the arithmetic; models routinely assert margins their own numbers contradict.
- Weak answer smell: sources cited for trivia while the load-bearing number floats free; ranges collapsing to point estimates mid-document.
- Does NOT apply: qualitative landscape questions with no numeric spine (rare in this product).

## Output contract
Revision must include an assumptions ledger (assumption → value → basis → sensitivity), pass internal-consistency arithmetic, and match precision to evidence.
