"""Validated storage and aggregation for official NBA game-level tracking."""

from collections import defaultdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "nba_tracking_games"
FEATURE_PATH = ROOT / "data" / "nba_tracking_features.json"
ENDPOINTS = {
    "player_track": "boxscoreplayertrackv3",
    "matchups": "boxscorematchupsv3",
    "hustle": "boxscorehustlev2",
}

TRACK_FIELDS = ("distance", "reboundChancesOffensive", "reboundChancesDefensive", "reboundChancesTotal",
                "touches", "secondaryAssists", "freeThrowAssists", "passes", "assists",
                "contestedFieldGoalsMade", "contestedFieldGoalsAttempted", "uncontestedFieldGoalsMade",
                "uncontestedFieldGoalsAttempted", "defendedAtRimFieldGoalsMade", "defendedAtRimFieldGoalsAttempted")
HUSTLE_FIELDS = ("contestedShots", "contestedShots2pt", "contestedShots3pt", "deflections", "chargesDrawn",
                 "screenAssists", "screenAssistPoints", "looseBallsRecoveredOffensive",
                 "looseBallsRecoveredDefensive", "looseBallsRecoveredTotal", "offensiveBoxOuts",
                 "defensiveBoxOuts", "boxOutPlayerTeamRebounds", "boxOutPlayerRebounds", "boxOuts")
MATCHUP_FIELDS = ("partialPossessions", "matchupMinutesSort", "switchesOn", "playerPoints", "teamPoints",
                  "matchupAssists", "matchupPotentialAssists", "matchupTurnovers", "matchupBlocks",
                  "matchupFieldGoalsMade", "matchupFieldGoalsAttempted", "matchupThreePointersMade",
                  "matchupThreePointersAttempted", "helpBlocks", "helpFieldGoalsMade", "helpFieldGoalsAttempted",
                  "matchupFreeThrowsMade", "matchupFreeThrowsAttempted", "shootingFouls")


def minutes_number(value):
    if value in (None, ""): return 0.0
    if isinstance(value, (int, float)): return float(value)
    parts = str(value).split(":")
    return float(parts[0]) + float(parts[1]) / 60 if len(parts) == 2 else float(value)


def _number(value):
    value = 0 if value in (None, "") else float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError("tracking values must be finite and non-negative")
    return value


def _teams(payload, root):
    box = payload.get(root)
    if not isinstance(box, dict):
        raise ValueError(f"missing {root}")
    return box, (box.get("homeTeam", {}), box.get("awayTeam", {}))


def parse_player_rows(payload, game_id, kind):
    root = {"player_track": "boxScorePlayerTrack", "hustle": "boxScoreHustle"}[kind]
    box, teams = _teams(payload, root)
    if str(box.get("gameId")) != str(game_id): raise ValueError("unexpected game ID")
    fields = TRACK_FIELDS if kind == "player_track" else HUSTLE_FIELDS
    rows, seen = [], set()
    for team in teams:
        for player in team.get("players", []):
            player_id = str(player.get("personId") or "")
            if not player_id or player_id in seen: raise ValueError("missing or duplicate player-game ID")
            seen.add(player_id)
            stats = player.get("statistics") or {}
            row = {"game_id": str(game_id), "player_id": player_id, "player_name": " ".join(filter(None, (player.get("firstName"), player.get("familyName")))),
                   "team_id": str(team.get("teamId") or ""), "minutes": minutes_number(stats.get("minutes")),
                   "source": f"NBA {ENDPOINTS[kind]}", "retrieved_at": datetime.now(timezone.utc).isoformat()}
            row.update({field: _number(stats.get(field)) for field in fields})
            for made, attempted in (("contestedFieldGoalsMade", "contestedFieldGoalsAttempted"),
                                    ("uncontestedFieldGoalsMade", "uncontestedFieldGoalsAttempted"),
                                    ("defendedAtRimFieldGoalsMade", "defendedAtRimFieldGoalsAttempted")):
                if made in row and row[made] > row[attempted]: raise ValueError(f"{made} exceeds attempts")
            rows.append(row)
    if not rows: raise ValueError("no player rows")
    return rows


def parse_matchup_rows(payload, game_id):
    box, teams = _teams(payload, "boxScoreMatchups")
    if str(box.get("gameId")) != str(game_id): raise ValueError("unexpected game ID")
    rows, seen = [], set()
    for defending_team in teams:
        for defender in defending_team.get("players", []):
            defender_id = str(defender.get("personId") or "")
            for offense in defender.get("matchups", []):
                offense_id = str(offense.get("personId") or "")
                key = (defender_id, offense_id)
                if not all(key) or key in seen: raise ValueError("missing or duplicate matchup key")
                seen.add(key)
                stats = offense.get("statistics") or {}
                row = {"game_id": str(game_id), "offensive_player_id": offense_id,
                       "defensive_player_id": defender_id, "defensive_player_name": " ".join(filter(None, (defender.get("firstName"), defender.get("familyName")))),
                       "source": "NBA boxscorematchupsv3", "retrieved_at": datetime.now(timezone.utc).isoformat()}
                row.update({field: _number(stats.get(field)) for field in MATCHUP_FIELDS})
                if row["matchupFieldGoalsMade"] > row["matchupFieldGoalsAttempted"] or row["helpFieldGoalsMade"] > row["helpFieldGoalsAttempted"]:
                    raise ValueError("matchup makes exceed attempts")
                rows.append(row)
    if not rows: raise ValueError("no matchup rows")
    return rows


def validate_payload(payload, game_id, kind):
    if not isinstance(payload, dict): raise ValueError("response is not a JSON object")
    return parse_matchup_rows(payload, game_id) if kind == "matchups" else parse_player_rows(payload, game_id, kind)


def cache_path(game_id, kind, cache_dir=CACHE_DIR):
    return Path(cache_dir) / str(game_id) / f"{kind}.json"


def atomic_json(path, payload):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.stem + "-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream: json.dump(payload, stream, separators=(",", ":"), allow_nan=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def save_validated(payload, game_id, season, kind, cache_dir=CACHE_DIR):
    rows = validate_payload(payload, game_id, kind)
    wrapper = {"schema_version": 1, "status": "verified", "game_id": str(game_id), "season": int(season),
               "kind": kind, "source": f"NBA {ENDPOINTS[kind]}", "rows": rows}
    atomic_json(cache_path(game_id, kind, cache_dir), wrapper)
    return wrapper


def load_games(cache_dir=CACHE_DIR):
    for path in Path(cache_dir).glob("*/*.json"):
        try:
            with path.open(encoding="utf-8") as handle: data = json.load(handle)
            if data.get("status") == "verified": yield data
        except (OSError, ValueError):
            continue


def aggregate(cache_dir=CACHE_DIR):
    players = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    games = defaultdict(set); source_games = defaultdict(set)
    for game in load_games(cache_dir):
        weight = {2025: 1.0, 2024: .65, 2023: .40}.get(game["season"], 1.0)
        kind = game["kind"]; source_games[kind].add(game["game_id"])
        for row in game["rows"]:
            player_id = row.get("defensive_player_id") if kind == "matchups" else row.get("player_id")
            games[(player_id, kind)].add(game["game_id"]); target = players[player_id][kind]
            target["weighted_games"] += weight
            target["tracked_minutes"] += row.get("minutes", row.get("matchupMinutesSort", 0) / 60) * weight
            for key, value in row.items():
                if key in {*TRACK_FIELDS, *HUSTLE_FIELDS, *MATCHUP_FIELDS}: target[key] += value * weight
    return {"players": {pid: {kind: {**dict(values), "unique_games": len(games[(pid, kind)])}
                                      for kind, values in kinds.items()} for pid, kinds in players.items()},
            "coverage": {kind: {"games_downloaded": len(ids)} for kind, ids in source_games.items()}}
