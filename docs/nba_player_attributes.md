# NBA player attributes

## Architecture

The franchise model keeps five layers separate: source snapshots, normalized player statistics, stable player identity mappings, calculated attributes, and simulation behavior. `nba_attribute_service.py` owns the rating schema and calculations. UI templates only render its results.

The current model is `v1` and uses a 25–99 scale. Ratings are league-percentile scores within broad position cohorts (guard, forward, center). A games-played reliability weight pulls small samples toward the cohort midpoint. Every result retains its season, games played, confidence, description, and model version.

Runtime joins use the stored ESPN-to-statistics player ID bridge in `data/nba_player_identity.csv`. Player names are used only by the offline mapping builder to propose exact matches. Ambiguous and missing matches remain unrated.

## Current ratings

| Attribute | Current feature | Context | Limitation |
| --- | --- | --- | --- |
| Scoring | Points per game | Position percentile | Measures scoring production, not shot quality |
| Playmaking | Assists per game | Position percentile | Potential assists and turnovers are not loaded |
| Rebounding | Rebounds per game | Position percentile | Rebound chances and box outs are not loaded |
| Steal / Hands | Steals per game | Position percentile | Deflections and matchup turnovers are not loaded |
| Rim Protection | Blocks per game | Position percentile | Rim contests and defended field-goal impact are not loaded |

Three-point volume is defined separately as a tendency. It uses made threes per game and is not presented as shooting ability.

## Adding an attribute

Add one centralized `AttributeDefinition`, ingest its raw features into a season snapshot, and calculate the feature without changing the UI. Set a sample target and source-confidence ceiling that match the statistic. Missing values must remain unavailable. Add a behavior frequency to `TENDENCY_DEFINITIONS`, not the skill schema.

## Next data to ingest

The next useful inputs from the workbook are field-goal attempts and percentages, free throws, offensive and defensive rebounds, turnovers, minutes, potential assists, rebound chances, defended shooting, hustle events, shot-location splits, and play-type possessions. These unlock true shooting skill, ball security, interior and perimeter defense, screening, finishing, and off-ball attributes.
