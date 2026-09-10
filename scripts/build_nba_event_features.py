"""Build validated NBA shot-location/action features from hoopR season releases.

The downloaded RDS files are temporary. Only compact, aggregated features and
their provenance are committed to the application data snapshot.
"""

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unicodedata
import sys

import pyreadr
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from nba_court_zones import classify_shot

OUTPUT = ROOT / "data" / "nba_event_features.json"
BASE_STATS = ROOT / "data" / "nba_franchise_stats_2025.csv"
URL = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_pbp/play_by_play_{season}.rds"
WEIGHTS = {2025: 1.0, 2024: .65, 2023: .40}
ACTION_WORDS = {"layup": "layup", "dunk": "dunk", "floating": "floater", "hook": "hook"}


def _normal(value):
    plain = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return " ".join(plain.casefold().split())


def _identity_by_name():
    matches = {}
    with BASE_STATS.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            matches.setdefault(_normal(row["player"]), set()).add(row["player_id"])
    return {name: next(iter(ids)) for name, ids in matches.items() if len(ids) == 1}


def normalize_coordinates(court_x, court_y):
    """Convert hoopR's full-court coordinates to lateral/forward feet from rim."""
    court_x, court_y = float(court_x), float(court_y)
    return court_y, 41.75 - abs(court_x)


def _download_frame(season, timeout):
    response = requests.get(URL.format(season=season), timeout=timeout)
    response.raise_for_status()
    handle, path = tempfile.mkstemp(prefix=f"nba-pbp-{season}-", suffix=".rds")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(response.content)
        return next(iter(pyreadr.read_r(path).values()))
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _increment(target, key, amount):
    target[key] = target.get(key, 0.0) + amount


def aggregate_frame(frame, season, identities, players):
    required = {"shooting_play", "season_type", "athlete_id_1", "athlete_name_1", "coordinate_x",
                "coordinate_y", "scoring_play", "score_value", "type_text", "text"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"hoopR {season} is missing required columns: {sorted(missing)}")
    shots = frame[(frame["shooting_play"] == True) & (frame["season_type"] == 2)]  # noqa: E712
    accepted = rejected = 0
    for row in shots.itertuples(index=False):
        stats_id = identities.get(_normal(row.athlete_name_1))
        if not stats_id or row.coordinate_x != row.coordinate_x or row.coordinate_y != row.coordinate_y:
            rejected += 1
            continue
        lateral, forward = normalize_coordinates(row.coordinate_x, row.coordinate_y)
        if not (-25.5 <= lateral <= 25.5 and -1 <= forward <= 47):
            rejected += 1
            continue
        zone = classify_shot(lateral, forward)
        weight = WEIGHTS.get(int(season), 1.0)
        made = bool(row.scoring_play) and float(row.score_value or 0) in (2, 3)
        target = players.setdefault(stats_id, {"player": str(row.athlete_name_1), "counts": {}, "seasons": set()})
        target["seasons"].add(int(season))
        _increment(target["counts"], "shot_fga", weight)
        _increment(target["counts"], f"{zone}_fga", weight)
        if made:
            _increment(target["counts"], "shot_fg", weight)
            _increment(target["counts"], f"{zone}_fg", weight)
        action_text = f"{row.type_text or ''} {row.text or ''}".casefold()
        for word, action in ACTION_WORDS.items():
            if word in action_text:
                _increment(target["counts"], f"{action}_fga", weight)
                if made: _increment(target["counts"], f"{action}_fg", weight)
                break
        assisted = "assist" in action_text
        if made:
            _increment(target["counts"], "assisted_fg" if assisted else "unassisted_fg", weight)
        accepted += 1
    return {"season": int(season), "rows": len(frame), "shot_rows": len(shots),
            "accepted_shots": accepted, "rejected_shots": rejected}


def _ratio(counts, made, attempted):
    return counts.get(made, 0) / counts.get(attempted, 0) if counts.get(attempted, 0) else None


def _finalize(player):
    counts = {key: round(value, 3) for key, value in player["counts"].items()}
    features = {}
    zone_groups = {
        "rim": ("rim",), "paint": ("paint",),
        "short_midrange": ("short-midrange-left", "short-midrange-center", "short-midrange-right"),
        "long_midrange": ("long-midrange-left", "long-midrange-center", "long-midrange-right", "left-baseline-midrange", "right-baseline-midrange", "left-elbow", "right-elbow"),
        "corner_three": ("left-corner-three", "right-corner-three"),
        "above_break_three": ("above-break-three-left", "above-break-three-center", "above-break-three-right", "deep-three-left", "deep-three-center", "deep-three-right"),
    }
    for feature, zones in zone_groups.items():
        attempts = sum(counts.get(f"{zone}_fga", 0) for zone in zones)
        makes = sum(counts.get(f"{zone}_fg", 0) for zone in zones)
        features[f"{feature}_fga"] = round(attempts, 3)
        features[f"{feature}_pct"] = round(makes / attempts, 5) if attempts else None
        features[f"{feature}_rate"] = round(attempts / counts["shot_fga"], 5) if counts.get("shot_fga") else None
    for action in ACTION_WORDS.values():
        features[f"{action}_fga"] = counts.get(f"{action}_fga", 0)
        features[f"{action}_pct"] = _ratio(counts, f"{action}_fg", f"{action}_fga")
    made = counts.get("shot_fg", 0)
    features["unassisted_make_rate"] = round(counts.get("unassisted_fg", 0) / made, 5) if made else None
    return {"player": player["player"], "seasons": sorted(player["seasons"], reverse=True),
            "counts": counts, "features": features,
            "provenance": {"source": "SportsDataverse hoopR ESPN NBA play-by-play", "method": "event-derived", "confidence": "medium-high"}}


def build(seasons, timeout=120):
    identities, players, sources = _identity_by_name(), {}, []
    for season in seasons:
        sources.append(aggregate_frame(_download_frame(season, timeout), season, identities, players))
    finalized = {player_id: _finalize(player) for player_id, player in players.items()}
    attempts = sum(player["counts"].get("shot_fga", 0) for player in finalized.values())
    return {"status": "verified", "schema_version": 1, "fetched_at": datetime.now(timezone.utc).isoformat(),
            "model_seasons": list(seasons), "players": finalized, "sources": sources,
            "coverage": {"matched_players": len(finalized), "weighted_shot_attempts": round(attempts),
                         "source_priority": "approved open fallback after official endpoint timeout"}}


def _atomic_write(payload):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix="nba-events-", suffix=".json", dir=OUTPUT.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        os.replace(temporary, OUTPUT)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, default=[2025, 2024, 2023])
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    payload = build(args.seasons, args.timeout)
    _atomic_write(payload)
    print(json.dumps(payload["coverage"], indent=2))


if __name__ == "__main__":
    main()
