# NBA player attributes

## v4 tracking-expanded update

## Multi-provider tracking layer (shadow mode)

`nba_tracking_providers.py` defines a vendor-neutral feature contract for drives,
passing, touches, rebound opportunities, hustle, screens, matchup events, defended
shooting, shot coordinates, and play types. Every value carries provider, dataset,
original field, player, season, optional game, retrieval time, sample, coverage,
access tier, and `DIRECT` / `DERIVED` / `PROXY` evidence classification. Provider
names remain distinct: `sportradar_nba` never means `sportradar_synergy`.

The configured source order is verified NBA Stats cache, licensed Sportradar NBA,
Synergy analytics, hoopR-derived fallback, then Not Tracked. Selection preserves
the winning feature's provenance. Source confidence reflects what the measurement
actually represents; it is combined with sample reliability when a future feature
is promoted.

The adapter reads credentials only from `SPORTRADAR_API_KEY` and
`SPORTRADAR_SYNERGY_API_KEY`; access tier and timeout are configured with
`SPORTRADAR_ACCESS_LEVEL` (`trial` or `production`) and
`SPORTRADAR_TIMEOUT_SECONDS`. Missing credentials and HTTP/schema failures produce
a controlled provider-unavailable result. Raw authenticated responses, headers,
cookies, sessions, account identifiers, and keys must never be committed.

Research findings are recorded in `data/nba_tracking_provider_matrix.json` and are
included by `scripts/report_nba_attribute_coverage.py`. Sportradar NBA documentation
confirms an official NBA API with game/player/season data, play-by-play, profiles,
splits, advanced metrics, and event positional data, but it does not document exact
equivalents for the blocked drive, passing, hustle, screen, chance, touch, movement,
or matchup fields. Those remain `UNKNOWN` or Not Tracked rather than guessed.

Synergy is treated as a separate manually tagged product. Its documented possession
events support isolation, post-up, pick-and-roll handler/roll-man, cut, transition,
spot-up, offensive-rebound, off-screen, and handoff classifications, plus NBA-only
big/small pick-and-roll defender roles, an optional defender, root/primary/secondary
players, outcomes, and shot coordinates. This can support future Synergy-derived
offensive and defensive play-type attributes and P&R screener involvement. It is
not a substitute definition for Second Spectrum direct matchup tracking, NBA drive
counts, or NBA screen assists.

All new adapters are intentionally **shadow-only**. They can emit old rating, new
rating, difference, source, and confidence comparisons, but `promoted` is always
false. The possession-expanded model is `v5-possession-expanded`; licensed tracking data is
available, representative coverage is measured, player and season IDs reconcile,
and basketball sanity checks pass for passers, defenders, scorers, rebounders,
screeners, specialists, and contrasting usage/turnover archetypes.

The current model combines NBA-wide, recency-weighted box-score features with
validated shot events from the 2022-23 through 2024-25 seasons. Shot-event data
comes from the SportsDataverse hoopR ESPN NBA play-by-play releases after the
official NBA statistics endpoint timed out. The browser never calls either
provider; ingestion is offline and the last verified cache is preserved.

The event pipeline converts full-court coordinates to feet from the nearest rim,
rejects out-of-bounds and unmatched records, classifies reusable court zones, and
stores only compact player aggregates with source and method metadata. Low samples
regress toward the midpoint and lower confidence rather than becoming false zeroes.
Unsupported tracking categories remain explicitly **Not tracked**.

Run `python scripts/report_nba_attribute_coverage.py` for the developer coverage,
source, season-validation, and not-tracked report.

## Official game tracking warehouse

`scripts/build_nba_tracking_warehouse.py` now implements validated, incremental
ingestion for `BoxScorePlayerTrackV3`, `BoxScoreMatchupsV3`, and
`BoxScoreHustleV2`. Each successful endpoint/game pair is committed atomically,
valid existing games are skipped by default, and failed calls are recorded without
removing earlier results. Matchup records preserve separate offensive and defensive
player IDs. Percentages are never averaged; raw makes, attempts, possessions,
minutes, chances, and events are accumulated before rates are calculated.

The current host times out on all three direct endpoint families. The normal NBA
Drives page does render, while automated headless Edge receives an Access Denied
page. No browser table has therefore been promoted into the model, and no blocked
tracking category has been converted into a fabricated rating.

## Model architecture

The franchise scouting pipeline is source snapshot → canonical player-season records → multi-season feature store → granular attributes → weighted summary ratings → simulation tendencies. `nba_attribute_service.py` owns definitions, transformations, reliability, calibration, confidence, aggregation, and profile assembly. UI templates render the resulting profile without calculating ratings.

The active model is `v5-possession-expanded`. Every skill rating uses one NBA-wide reference population. Position percentile remains available as scouting context but never drives the final rating. The five compact roster summaries remain Scoring, Playmaking, Rebounding, Steal / Hands, and Rim Protection.

## Source snapshot

`scripts/build_nba_franchise_stats.py` now caches three completed seasons (2022–23 through 2024–25) from the project's existing curated player-totals source. The snapshot contains:

- games, starts, and minutes;
- field goals and attempts;
- 2PT, 3PT, and free-throw makes, attempts, and percentages;
- effective field-goal percentage;
- offensive, defensive, and total rebounds;
- assists, steals, blocks, turnovers, fouls, points, and triple-doubles.

Runtime roster joins continue to use the validated ESPN-to-statistics identity bridge. Frontend code never calls an external provider.

`scripts/build_nba_official_features.py` is the offline official-data adapter. It requests Advanced, Hustle, Catch/Shoot, Pull-Up, Drives, Passing, and Rebounding Tracking datasets for the same three seasons, reconciles NBA player names to stable local statistics IDs, and writes one atomic JSON snapshot. The existing verified snapshot is never overwritten when an endpoint fails. `nba_official_features.py` exposes the optional cache to the model and returns a safe missing or invalid state instead of raising during a web request.

## Multi-season true talent

The current season, prior season, and two-seasons-prior totals use weights of 1.00, 0.65, and 0.40. Weighted counting inputs are combined before rate and efficiency metrics are calculated. This keeps established skills stable when the newest season is small. Recent form is deliberately not mixed into permanent ratings.

## League-wide normalization

Each derived metric is compared with all qualifying NBA players. The observed NBA-wide percentile is blended toward the league midpoint according to metric-specific reliability, then mapped onto the 25–99 scale. Position percentile is calculated independently and displayed only as context.

Attempt-based skills use attempts. Decision metrics use assists plus turnovers. Production rates use minutes. This replaces the old games-played reliability denominator. Three-point ability also applies a low-usage penalty below 75 weighted attempts so non-shooters and tiny samples do not receive an average or elite result from statistical uncertainty.

## Implemented granular attributes

| Category | Attribute | Derived input | Reliability sample |
| --- | --- | --- | --- |
| Scoring | Scoring Volume | PTS per 36 | Minutes |
| Scoring | Scoring Efficiency | True shooting percentage | Shooting possessions |
| Shooting | Field Goal Efficiency | Effective FG% | FGA |
| Shooting | Three-Point Shooting | 3P% | 3PA |
| Shooting | Two-Point Shooting | 2P% | 2PA |
| Shooting | Free Throw | FT% | FTA |
| Playmaking | Assist Creation | AST per 36 | Minutes |
| Playmaking | Assist-to-Turnover | AST / TOV | Decisions |
| Playmaking | Turnover Avoidance | Inverse TOV per 36 | Minutes |
| Rebounding | Total Rebounding | REB per 36 | Minutes |
| Rebounding | Offensive Rebounding | OREB per 36 | Minutes |
| Rebounding | Defensive Rebounding | DREB per 36 | Minutes |
| Steal / Hands | Steal Ability | STL per 36 | Minutes |
| Interior Defense | Shot Blocking | BLK per 36 | Minutes |
| Interior Defense | Foul Discipline | Inverse PF per 36 | Minutes |

## Tendencies

Five behavior ratings remain separate from ability: Three-Point Attempt, Free Throw Rate, Shot Volume, Pass Activity, and Offensive Rebound Activity. They use frequency or production-share measures and do not feed unrelated skill ratings.

## Summary formulas

Summary weights are centralized. Low-confidence children below the minimum aggregation confidence are excluded.

- Scoring: Scoring Volume 42%, Scoring Efficiency 28%, Field Goal Efficiency 15%, Three-Point Shooting 8%, Free Throw 7%.
- Playmaking: Assist Creation 55%, Assist-to-Turnover 30%, Turnover Avoidance 15%.
- Rebounding: Total 40%, Offensive 30%, Defensive 30%.
- Steal / Hands: Steal Ability 100% until deflection and loose-ball data is available.
- Rim Protection: Shot Blocking 100% until defended-rim data is available.

## Missing data and confidence

Missing, zero, and low usage are distinct. Missing data produces `Not tracked`; an actual zero remains zero; low-volume action skills are reliability-adjusted. Unsupported categories never lower a summary. Profiles retain observed values, raw weighted samples, NBA and position percentiles, reliability, confidence, source metric, reference population, model version, source seasons, and calculation timestamp.

## Court zones

`nba_court_zones.classify_shot()` centrally classifies rim, paint, short and long midrange, baseline, elbow, left/right corner three, left/center/right above-the-break three, and deep-three areas. It expects coordinates in feet from the rim. Zone ratings remain unavailable until shot-coordinate ingestion is added.

## Data still needed

The next source phase should ingest official advanced player stats and shot charts, followed by shooting-context splits, drives, passing, rebound tracking, hustle, defended shots, matchups, play types, and on/off context. Those sources are required for catch-and-shoot and pull-up skill, court-zone accuracy, finishing, ball handling, potential-assist playmaking, rebound opportunity conversion, perimeter defense, defended-rim impact, screening, hustle, and play-type attributes. None should be inferred from unrelated box-score statistics.

When the adapter was added, `stats.nba.com` timed out from the development host while public NBA.com statistics pages remained reachable. No failed or partial tracking snapshot is committed. The model therefore continues to label tracking-only categories `Not tracked`. Run the official feature builder from a network path accepted by the NBA endpoint before enabling those attributes.
