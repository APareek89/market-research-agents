---
id: scenario-sensitivity
name: Scenario & Sensitivity Discipline (Outside View)
cluster: decision-risk
origin: Shell scenario planning; Kahneman/Tversky reference-class forecasting; tornado analysis
strength: Replaces single-point futures with ranges, driver sensitivities, and base-rate honesty
trigger_signals: [forecast, projection, CAGR, by 2030, growth assumption, market will reach, business case]
when_to_use: Any draft whose recommendation depends on a forecast or point estimate of the future
reviewer: [vera]
pairs_well_with: [assumption-audit, premortem, expected-value-decision]
failure_modes_caught: [single-point forecasting, inside-view optimism, sensitivity-free models, CAGR worship]
---

## Essence
The future arrives as a distribution, not a number. Sound analysis shows bear/base/bull scenarios built from DRIVERS (not ±20% on the answer), ranks which driver moves the outcome most (tornado logic), and disciplines optimism with the outside view: what actually happened to the reference class of similar attempts.

## Interrogation set
1. Where is the bear case? Not the base case minus 20% — a coherent story of what the world looks like when the thesis is wrong.
2. Which single driver, varied across its plausible range, swings the outcome most? Does the draft even rank its drivers?
3. Outside view: of the last ~10 comparable attempts (similar products, similar markets), what fraction succeeded, and what did the median achieve? Why is this case different — specifically?
4. At which driver value does the recommendation FLIP? Is that threshold inside or outside the plausible range?
5. Is the quoted CAGR from a sell-side report compounding an early-adopter base — and does the draft's own bottom-up math reproduce it?
6. Under the bear case: is the recommendation still right, wrong-but-recoverable, or ruinous? That classification IS the risk assessment.

## How to apply
- Three scenarios max, each driver-derived and internally coherent; more is theater.
- Weak answer smell: hockey-sticks with no flat-case; "conservative" estimates that are 80% of aggressive ones; no flip-point stated.
- Does NOT apply: descriptive current-state questions with no forward claim.

## Output contract
Revision must include bear/base/bull built from named drivers, a driver-sensitivity ranking, the recommendation's flip-point, and one outside-view reference-class comparison.
