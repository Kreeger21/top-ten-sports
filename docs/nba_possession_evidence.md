# NBA possession evidence

The `v1-possession-context` dataset complements, rather than replaces, the existing
hoopR event pipeline. `pbpstats==1.3.11` is integrated through a public-object
adapter. Live validation found that its `stats_nba` provider returned an
incompatible response and its `data_nba` provider returned HTTP 403, so the local
production snapshot uses structured SportsDataverse hoopR ESPN play-by-play.

## Canonical representation

Each local possession records game, season, period, start/end clocks, duration,
teams, reconstructed five-player units where available, start/end classifications,
observable events, final shot/assist/turnover/steal/rebound/foul/free-throw facts,
points, transition class and confidence, plus source lineage. The compressed
JSONL is the auditable possession store; `nba_possession_features.json` is the
compact application snapshot.

Start types are based on the previous structured terminal event. End types are
based on structured turnovers, field goals, rebounds, free throws, and period
events. A multi-signal transition classifier combines live-ball starts, steals,
short duration, early shots, explicit fast-break text, and results. Ambiguous
possessions remain `Unknown`; confidence weights transition aggregates.

## Skills, context, and tendencies

- Skill: possession shot creation uses observable unassisted makes per 100
  reconstructed on-court possessions. It never labels missed attempts assisted or
  unassisted because ordinary play-by-play cannot establish that fact.
- Skill: handle security uses turnovers per creation event and excludes passing
  quality from its primary calculation.
- Skill: transition scoring, post-action scoring and second-chance scoring use
  their own action-specific sample denominators.
- Tendency: assisted/unassisted make share, transition frequency and post frequency
  remain separate from ability.
- Context: Creation Burden is shots + assists + turnovers per 100 known on-court
  offensive possessions. Creator roles use NBA-population median and upper-quartile
  boundaries rather than named-player rules.
- Impact: reconstructed-possession on/off ORtg and DRtg are stored for diagnostics
  and are not fed into Overall.

Lineups are reconstructed from first-quarter actions and substitution sequences.
Only possessions with five unique players for both teams enter lineup/on-off
metrics. The snapshot reports this coverage; no missing unit is imputed.

## Known limits

Ordinary ESPN play-by-play does not contain every pass, touch, defender, matchup,
rebound opportunity, or optical movement. Therefore this phase does not publish
potential assists, secondary assists, drives, rebound chances, perimeter defense,
interior defense, or optical tracking claims. Multi-team on/off is contextual and
should not be interpreted as individual defensive skill. A full RAPM/WOWY model is
deliberately out of scope.

The Overall curve, position baselines, position weights, penalties, and bonuses
remain frozen at `v2-positional-value`.
