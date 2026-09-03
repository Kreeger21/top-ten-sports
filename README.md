# Top Ten Sports

A Flask web app with MLB, NFL, NBA, and College Football top-ten leaderboards, randomizers, and guessing challenges.

## Run locally

### Test environment

```powershell
.\run-test.cmd
```

Then open <http://127.0.0.1:5000> in your browser.

The test environment enables Flask's debugger and automatically reloads edited code.

### Production environment

```powershell
.\run-production.cmd
```

Then open <http://127.0.0.1:8000>. Production uses Waitress with debugging disabled.

### Verify before promotion

```powershell
.\verify.cmd
```

The intended Git workflow is to edit and test on `develop`, run verification, and merge into `main` for production. Git branches will be initialized after an author name and email are configured.

The main home screen lets users enter the MLB, NFL, or NBA version. Each sport then offers custom leaderboards, randomized lists, and Top Ten Challenge mode.

## Current statistics

### MLB

- Hitting: batting average, home runs, RBI, hits, stolen bases, batting WAR
- Pitching: ERA, wins, strikeouts, WHIP, saves, pitching WAR

Rate statistics use MLB's qualified-player pool. Counting statistics include all players.
WAR uses Baseball-Reference bWAR through pybaseball and may differ from FanGraphs WAR.

### NFL

- Passing: yards, touchdowns, completions, attempts, interceptions
- Rushing: yards, touchdowns, attempts, first downs
- Receiving: yards, touchdowns, receptions
- Fantasy: standard and PPR fantasy points

NFL regular-season leaderboards use nflverse and currently cover 1999–2025. Offensive Fill the Field combines nflverse with a checked-in historical Sports Reference extract for regular-season passing, rushing, and receiving records from 1950–2025. Defensive Fill the Field uses official sacks from 1982, tackles and position-specific interceptions from 1994, and tackles for loss and forced fumbles from 1999, all through 2025. The compact historical files can be reproduced with the scripts in `scripts/`.

### NBA

- Scoring: points, three-pointers, and shooting percentages
- Rebounding: total, offensive, and defensive rebounds
- Playmaking: assists and assist-to-turnover ratio
- Defense: steals and blocks

NBA regular-season leader data comes from the official NBA statistics service. Enter the season's starting year; for example, `2023` represents 2023–24.
NBA leaderboards use a fixed qualification of at least 65 games played.

### College Football

- Passing: yards, touchdowns, completions, attempts, interceptions
- Rushing: yards, touchdowns, attempts
- Receiving: yards, touchdowns, receptions, targets
- Defense: interceptions, sacks, forced fumbles, pass breakups
- Kicking: field goals made and attempted

College Football rushing data covers 1996–2026. Other College Football categories cover 2014–2026. Results are restricted to Division I FBS conferences and teams. Rushing uses official season-summary totals from the D1SportsNet NCAA statistics archive so postseason games and official corrections are included. Other categories use cfbfastR play data.

## Public deployment

The included `render.yaml` deploys the `main` branch as a Render web service. Render installs `requirements.txt`, starts the app with Gunicorn, generates the Flask session secret, and redeploys production whenever `main` is updated.
Targets are not offered because Sports-Reference does not publish CFB target totals and the older play-level target data is incomplete.
