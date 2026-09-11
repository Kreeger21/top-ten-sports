# NBA Overall calibration log

## Iteration 1 — v2 positional architecture

- Replaced the universal six-summary weighted average with centralized G/F/C models.
- Added smooth core-deficiency penalties, outlier bonuses, coverage, confidence, and a logistic display curve.
- Result: C mean 81.38 versus G 70.74 and F 67.83; centers remained structurally inflated.

## Iteration 2 — positional baseline calibration

- Added raw-score offsets: G `0`, F `+2.5`, C `-8.0`.
- Reason: universal league percentiles make center-relevant rebound/block/finishing production abundant, while several currently unavailable guard/wing tracking groups are represented by conservative proxies.
- This changes Overall value only. Universal granular and summary attributes remain untouched.
- No player-specific adjustment or positional quota is used.

## Input-integrity pass — five-position metadata and evidence quality

- Overall weights, curve, penalties, bonuses, and positional offsets were frozen.
- Replaced broad ESPN G/F/C where possible with PG/SG/SF/PF/C from the verified season-statistics identity mapping.
- Added explicit Direct/Derived/Proxy/Fallback evidence classifications and confidence regression toward neutral for low-quality groups.
- Ty Jerome root cause: high-efficiency/volume scoring and assist production was reused across Shot Creation, Ball Handling, Off-Ball, Transition, and Perimeter Defense proxies, falsely yielding 100% high-confidence coverage.
- Effect: Ty Jerome moved from 88 to 81, but the league now has no 85+ players. This reveals that current creation/handling/defense evidence is insufficient and must be enriched before recalibrating the frozen display curve.
# Possession-evidence phase

The attribute model advanced to `v5-possession-expanded`; the Overall model remains
frozen at `v2-positional-value`. A three-season hoopR fallback reconstructed 773,875
possessions across 3,697 games and 770 players. Complete unique 5-on-5 lineup
coverage is 71.9%; incomplete units are excluded from on/off.

The evidence upgrade replaced the generic Transition fallback, made Ball Handling
responsibility-aware, and added observable unassisted-make volume to Shot Creation.
It deliberately does not infer assist status for misses. With the frozen Overall
formula, the maximum is 84, with 13 players at 80+, zero at 85+, and zero at 90+.
Maximum raw positional value is 78.62. This supports a separate display-curve
calibration phase; remaining missing optical evidence must continue to be reported.
