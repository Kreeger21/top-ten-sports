# Top Ten Sports

A Flask web app with MLB, NFL, and NBA top-ten leaderboards, randomizers, and guessing challenges.

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
- Receiving: yards, touchdowns, receptions, targets
- Fantasy: standard and PPR fantasy points

NFL regular-season data comes from nflverse and currently covers 1999–2024.

### NBA

- Scoring: points, three-pointers, and shooting percentages
- Rebounding: total, offensive, and defensive rebounds
- Playmaking: assists and assist-to-turnover ratio
- Defense: steals and blocks

NBA regular-season leader data comes from the official NBA statistics service. Enter the season's starting year; for example, `2023` represents 2023–24.
NBA leaderboards use a fixed qualification of at least 65 games played.
