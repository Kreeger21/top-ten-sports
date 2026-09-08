"""Versioned, data-driven NBA franchise attribute calculations."""

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


MODEL_VERSION = "v1"
RATING_MIN, RATING_MAX = 25, 99
DATA_DIR = Path(__file__).with_name("data")


@dataclass(frozen=True)
class AttributeDefinition:
    id: str
    name: str
    category: str
    feature: str
    description: str
    source_confidence: float
    sample_target: int = 60


ATTRIBUTE_DEFINITIONS = (
    AttributeDefinition("scoring", "Scoring", "Offense", "pts", "League-relative points per game.", .80),
    AttributeDefinition("playmaking", "Playmaking", "Playmaking", "ast", "Position-relative assists per game.", .85),
    AttributeDefinition("rebounding", "Rebounding", "Rebounding", "trb", "Position-relative rebounds per game.", .85),
    AttributeDefinition("steal_hands", "Steal / Hands", "Defense", "stl", "Steals per game; deflection data is not yet available.", .65),
    AttributeDefinition("rim_protection", "Rim Protection", "Defense", "blk", "Blocks per game; defended-rim context is not yet available.", .65),
)

TENDENCY_DEFINITIONS = (
    AttributeDefinition("three_point_volume", "Three-Point Volume", "Tendency", "x3p", "Made threes per game as a shooting-volume proxy.", .60),
)


def _primary_position(position):
    position = (position or "").split("-")[0]
    if position in {"PG", "SG", "G"}: return "G"
    if position in {"SF", "PF", "F"}: return "F"
    return "C" if position == "C" else "ALL"


@lru_cache(maxsize=1)
def _stats():
    with (DATA_DIR / "nba_franchise_stats_2025.csv").open(encoding="utf-8") as handle:
        return tuple(csv.DictReader(handle))


@lru_cache(maxsize=1)
def _canonical_stats():
    by_player = {}
    for row in _stats():
        by_player.setdefault(row["player_id"], []).append(row)
    return tuple(next((row for row in rows if row["team"] == "TOT"), rows[0])
                 for rows in by_player.values())


@lru_cache(maxsize=1)
def _identity():
    with (DATA_DIR / "nba_player_identity.csv").open(encoding="utf-8") as handle:
        return {row["espn_player_id"]: row["stats_player_id"] for row in csv.DictReader(handle)
                if row["review_status"] == "auto_verified" and row["stats_player_id"]}


def _percentile(value, cohort):
    if not cohort: return .5
    return sum(candidate <= value for candidate in cohort) / len(cohort)


@lru_cache(maxsize=1024)
def attributes_for_player(espn_player_id):
    stats_id = _identity().get(str(espn_player_id))
    row = next((item for item in _canonical_stats() if item["player_id"] == stats_id), None)
    if row is None or not row.get("g"):
        return None
    games = float(row["g"])
    position = _primary_position(row["pos"])

    def calculate(definition):
        if not row.get(definition.feature): return None
        observed = float(row[definition.feature]) / games
        cohort = [float(item[definition.feature]) / float(item["g"]) for item in _canonical_stats()
                  if item.get(definition.feature) and item.get("g")
                  and _primary_position(item["pos"]) == position]
        if len(cohort) < 20:
            cohort = [float(item[definition.feature]) / float(item["g"]) for item in _canonical_stats()
                      if item.get(definition.feature) and item.get("g")
                      and _primary_position(item["pos"]) == position]
        reliability = min(1.0, games / definition.sample_target)
        adjusted = reliability * _percentile(observed, cohort) + (1 - reliability) * .5
        rating = round(RATING_MIN + adjusted * (RATING_MAX - RATING_MIN))
        return {"id": definition.id, "name": definition.name, "rating": rating,
                "tier": "elite" if rating >= 85 else ("strong" if rating >= 70 else "standard"),
                "confidence": round(reliability * definition.source_confidence * 100),
                "description": definition.description, "observed": round(observed, 2)}

    return {"model_version": MODEL_VERSION, "season": "2024–25", "games": int(games),
            "attributes": tuple(filter(None, (calculate(item) for item in ATTRIBUTE_DEFINITIONS))),
            "tendencies": tuple(filter(None, (calculate(item) for item in TENDENCY_DEFINITIONS)))}
