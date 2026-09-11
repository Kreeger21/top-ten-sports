"""League-wide, multi-season NBA franchise scouting profiles."""

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import nba_official_features
import nba_event_features
import nba_possession_service

MODEL_VERSION = "v5-possession-expanded"
MODEL_SEASON = "2022–23 through 2024–25"
REFERENCE_POPULATION = "NBA-wide"
RATING_MIN, RATING_MAX = 25, 99
DATA_DIR = Path(__file__).with_name("data")
SEASON_WEIGHTS = {2025: 1.0, 2024: .65, 2023: .40}
DERIVED_BOX_METRICS = {"pts_per36", "fga_per36", "ast_per36", "tov_per36", "trb_per36", "orb_per36",
                       "drb_per36", "stl_per36", "blk_per36", "pf_per36", "effective_fg", "true_shooting",
                       "three_pct", "two_pct", "ft_pct", "ast_tov", "three_attempt_rate", "free_throw_rate"}
BOX_SAMPLES = {"minutes", "shooting_possessions", "fga", "x3pa", "x2pa", "fta", "decisions"}


@dataclass(frozen=True)
class AttributeDefinition:
    id: str
    name: str
    category: str
    metric: str
    description: str
    sample_metric: str
    sample_target: float
    source_confidence: float
    inverse: bool = False
    zero_usage_is_low: bool = False
    low_usage_threshold: float = 0
    source: str = "Basketball Reference season totals"


ATTRIBUTE_DEFINITIONS = (
    AttributeDefinition("scoring_volume", "Scoring Volume", "Scoring", "pts_per36", "Points produced per 36 minutes.", "minutes", 1600, .88),
    AttributeDefinition("scoring_efficiency", "Scoring Efficiency", "Scoring", "true_shooting", "True shooting percentage using field-goal and free-throw attempts.", "shooting_possessions", 700, .90),
    AttributeDefinition("overall_shooting", "Field Goal Efficiency", "Shooting", "effective_fg", "Effective field-goal percentage, including the added value of threes.", "fga", 700, .92),
    AttributeDefinition("three_point_shooting", "Three-Point Shooting", "Shooting", "three_pct", "Three-point accuracy with attempt-based reliability and a low-usage penalty.", "x3pa", 300, .94, zero_usage_is_low=True, low_usage_threshold=75),
    AttributeDefinition("two_point_shooting", "Two-Point Shooting", "Shooting", "two_pct", "Two-point accuracy; shot-location detail is not yet available.", "x2pa", 500, .92),
    AttributeDefinition("free_throw_shooting", "Free Throw", "Shooting", "ft_pct", "Free-throw accuracy with attempt-based reliability.", "fta", 180, .96, zero_usage_is_low=True),
    AttributeDefinition("assist_creation", "Assist Creation", "Playmaking", "ast_per36", "Assists produced per 36 minutes.", "minutes", 1500, .88),
    AttributeDefinition("assist_turnover", "Assist-to-Turnover", "Playmaking", "ast_tov", "Assists created per turnover.", "decisions", 450, .86),
    AttributeDefinition("turnover_avoidance", "Turnover Avoidance", "Playmaking", "tov_per36", "Turnovers per 36 minutes; lower is better.", "minutes", 1500, .72, inverse=True),
    AttributeDefinition("total_rebounding", "Total Rebounding", "Rebounding", "trb_per36", "Total rebounds secured per 36 minutes.", "minutes", 1500, .90),
    AttributeDefinition("offensive_rebounding", "Offensive Rebounding", "Rebounding", "orb_per36", "Offensive rebounds secured per 36 minutes.", "minutes", 1500, .88),
    AttributeDefinition("defensive_rebounding", "Defensive Rebounding", "Rebounding", "drb_per36", "Defensive rebounds secured per 36 minutes.", "minutes", 1500, .88),
    AttributeDefinition("steal_ability", "Steal Ability", "Steal / Hands", "stl_per36", "Steals produced per 36 minutes.", "minutes", 1500, .78),
    AttributeDefinition("shot_blocking", "Shot Blocking", "Interior Defense", "blk_per36", "Blocks produced per 36 minutes.", "minutes", 1500, .74),
    AttributeDefinition("foul_discipline", "Foul Discipline", "Interior Defense", "pf_per36", "Personal fouls per 36 minutes; lower is better.", "minutes", 1500, .68, inverse=True),
    AttributeDefinition("rim_finishing", "At-Rim Finishing", "Finishing", "rim_pct", "Accuracy within four feet of the rim.", "rim_fga", 220, .90, source="SportsDataverse hoopR play-by-play"),
    AttributeDefinition("paint_finishing", "Paint Finishing", "Finishing", "paint_pct", "Accuracy in the paint outside the immediate rim area.", "paint_fga", 160, .84, source="SportsDataverse hoopR play-by-play"),
    AttributeDefinition("layup_finishing", "Layup Finishing", "Finishing", "layup_pct", "Accuracy on play-by-play events identified as layups.", "layup_fga", 180, .86, source="SportsDataverse hoopR play-by-play"),
    AttributeDefinition("dunk_finishing", "Dunk Finishing", "Finishing", "dunk_pct", "Accuracy on play-by-play events identified as dunks.", "dunk_fga", 100, .88, source="SportsDataverse hoopR play-by-play"),
    AttributeDefinition("floater_finishing", "Floater Finishing", "Finishing", "floater_pct", "Accuracy on floating-shot events.", "floater_fga", 90, .78, source="SportsDataverse hoopR play-by-play"),
    AttributeDefinition("short_midrange", "Short Midrange", "Shooting", "short_midrange_pct", "Accuracy on short non-paint two-point shots.", "short_midrange_fga", 130, .82, source="SportsDataverse hoopR play-by-play"),
    AttributeDefinition("long_midrange", "Long Midrange", "Shooting", "long_midrange_pct", "Accuracy on long two-point shots, including baseline and elbow areas.", "long_midrange_fga", 130, .82, source="SportsDataverse hoopR play-by-play"),
    AttributeDefinition("corner_three", "Corner Three", "Shooting", "corner_three_pct", "Accuracy from both three-point corners.", "corner_three_fga", 120, .86, source="SportsDataverse hoopR play-by-play"),
    AttributeDefinition("above_break_three", "Above-the-Break Three", "Shooting", "above_break_three_pct", "Accuracy on above-the-break and deep threes.", "above_break_three_fga", 240, .86, source="SportsDataverse hoopR play-by-play"),
    AttributeDefinition("self_created_scoring", "Self-Created Scoring", "Scoring", "unassisted_make_rate", "Share of made field goals not identified as assisted in play-by-play.", "shot_fg", 300, .72, source="SportsDataverse hoopR play-by-play"),
    AttributeDefinition("hook_scoring", "Hook Shot Making", "Finishing", "hook_pct", "Accuracy on explicitly classified hook-shot actions; not a complete post-up metric.", "hook_fga", 120, .74, source="SportsDataverse hoopR play-by-play"),
    AttributeDefinition("possession_self_creation", "Possession Shot Creation", "Scoring", "pos_self_created_makes_per_100", "Observable unassisted made field goals per 100 reconstructed on-court possessions; misses are not guessed.", "pos_creation_events", 900, .78, source="Derived Possession Evidence"),
    AttributeDefinition("possession_playmaking", "Possession Playmaking", "Playmaking", "pos_assists_per_100", "Assists per 100 reconstructed on-court offensive possessions.", "pos_offensive_possessions", 1500, .78, source="Derived Possession Evidence"),
    AttributeDefinition("passing_security", "Passing Security", "Playmaking", "pos_passing_security", "Assists as a share of recorded assist and turnover decisions.", "pos_creation_events", 900, .72, source="Derived Possession Evidence"),
    AttributeDefinition("handle_security", "Handle Security", "Ball Handling", "pos_handle_security", "Share of offensive creation events completed without a turnover.", "pos_creation_events", 900, .74, source="Derived Possession Evidence"),
    AttributeDefinition("off_ball_scoring", "Off-Ball Scoring Evidence", "Scoring", "pos_assisted_makes_per_100", "Assisted made field goals per 100 reconstructed on-court possessions; assistance is evidence, not proof, of off-ball skill.", "pos_assisted_fgm", 300, .70, source="Derived Possession Evidence"),
    AttributeDefinition("transition_scoring", "Transition Scoring", "Finishing", "pos_transition_points_per_possession", "Points per confidence-weighted transition possession.", "pos_transition_possessions", 220, .72, source="Derived Possession Evidence"),
    AttributeDefinition("post_possession_scoring", "Post Possession Scoring", "Finishing", "pos_post_efficiency", "Field-goal accuracy on explicitly identified post-action possessions.", "pos_post_fga", 140, .68, source="Derived Possession Evidence"),
    AttributeDefinition("second_chance_scoring", "Second-Chance Scoring", "Finishing", "pos_second_chance_points_per_action", "Points after an offensive rebound within the same possession.", "pos_second_chance_actions", 100, .68, source="Derived Possession Evidence"),
)

TENDENCY_DEFINITIONS = (
    AttributeDefinition("three_point_attempt", "Three-Point Attempt", "Shooting", "three_attempt_rate", "Share of field-goal attempts taken from three.", "fga", 600, .92),
    AttributeDefinition("free_throw_rate", "Free Throw Rate", "Scoring", "free_throw_rate", "Free-throw attempts per field-goal attempt.", "fga", 600, .88),
    AttributeDefinition("shot_volume", "Shot Volume", "Scoring", "fga_per36", "Field-goal attempts per 36 minutes.", "minutes", 1500, .88),
    AttributeDefinition("pass_activity", "Pass Activity", "Playmaking", "ast_per36", "Assist production as a current passing-frequency proxy.", "minutes", 1500, .62),
    AttributeDefinition("offensive_rebound_activity", "Offensive Rebound Activity", "Rebounding", "orb_per36", "Offensive-rebound activity per 36 minutes.", "minutes", 1500, .72),
    AttributeDefinition("rim_attempt", "Rim Attempt Rate", "Finishing", "rim_rate", "Share of shots attempted at the rim.", "shot_fga", 500, .90, source="SportsDataverse hoopR play-by-play"),
    AttributeDefinition("midrange_attempt", "Midrange Attempt Rate", "Shooting", "midrange_rate", "Share of shots attempted from short and long midrange.", "shot_fga", 500, .86, source="SportsDataverse hoopR play-by-play"),
    AttributeDefinition("corner_three_attempt", "Corner Three Rate", "Shooting", "corner_three_rate", "Share of shots attempted from the corners.", "shot_fga", 500, .88, source="SportsDataverse hoopR play-by-play"),
    AttributeDefinition("self_creation_tendency", "Self-Creation Tendency", "Scoring", "pos_unassisted_make_rate", "Share of made field goals recorded without an assist; missed-attempt creation is unknown.", "pos_fgm", 350, .76, source="Derived Possession Evidence"),
    AttributeDefinition("assisted_scoring_tendency", "Assisted Scoring Tendency", "Scoring", "pos_assisted_make_rate", "Share of made field goals identified as assisted.", "pos_fgm", 350, .76, source="Derived Possession Evidence"),
    AttributeDefinition("transition_tendency", "Transition Tendency", "Finishing", "pos_transition_frequency", "Confidence-weighted transition possessions as a share of known on-court offensive possessions.", "pos_offensive_possessions", 1200, .68, source="Derived Possession Evidence"),
    AttributeDefinition("post_tendency", "Post Tendency", "Finishing", "pos_post_tendency", "Explicit post actions as a share of known on-court offensive possessions.", "pos_offensive_possessions", 1200, .68, source="Derived Possession Evidence"),
)

SUMMARY_DEFINITIONS = (
    ("scoring", "Scoring", (("scoring_volume", .42), ("scoring_efficiency", .28), ("overall_shooting", .15), ("three_point_shooting", .08), ("free_throw_shooting", .07))),
    ("playmaking", "Playmaking", (("possession_playmaking", .30), ("passing_security", .15), ("assist_creation", .30), ("assist_turnover", .15), ("turnover_avoidance", .10))),
    ("rebounding", "Rebounding", (("total_rebounding", .40), ("offensive_rebounding", .30), ("defensive_rebounding", .30))),
    ("steal_hands", "Steal / Hands", (("steal_ability", 1.0),)),
    ("rim_protection", "Rim Protection", (("shot_blocking", 1.0),)),
    ("finishing", "Finishing", (("rim_finishing", .30), ("paint_finishing", .20), ("layup_finishing", .20), ("dunk_finishing", .18), ("floater_finishing", .12))),
)

CATEGORY_DESCRIPTIONS = {
    "Scoring": "NBA-wide scoring volume and efficiency.",
    "Shooting": "NBA-wide shooting efficiency with attempt-based reliability.",
    "Finishing": "Validated rim, paint, layup, dunk, and floater results derived from shot events.",
    "Playmaking": "NBA-wide assist creation, decision efficiency, and ball security proxies.",
    "Ball Handling": "Possession-responsibility ball security; optical dribble and pressure tracking are not loaded.",
    "Rebounding": "NBA-wide offensive, defensive, and total rebound production.",
    "Perimeter Defense": "Matchup shooting, contests, and deflections are not loaded.",
    "Interior Defense": "Shot blocking and foul discipline; defended-rim impact is not loaded.",
    "Steal / Hands": "Steal production; deflections and loose balls are not loaded.",
    "Hustle": "Hustle tracking is not present in the local snapshot.",
    "Screening": "Screen assists and screening possessions are not loaded.",
}


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
def _identity():
    with (DATA_DIR / "nba_player_identity.csv").open(encoding="utf-8") as handle:
        return {row["espn_player_id"]: row["stats_player_id"] for row in csv.DictReader(handle)
                if row["review_status"] == "auto_verified" and row["stats_player_id"]}


def _canonical_rows():
    by_key = {}
    for row in _stats():
        by_key.setdefault((row["player_id"], int(row["season"])), []).append(row)
    return tuple(next((row for row in rows if row["team"] == "TOT"), rows[0]) for rows in by_key.values())


def _number(row, key):
    value = row.get(key)
    return float(value) if value not in (None, "") else 0.0


def _blend(rows):
    totals = {}
    for row in rows:
        weight = SEASON_WEIGHTS.get(int(row["season"]), 0)
        for key in ("g", "gs", "mp", "fg", "fga", "x3p", "x3pa", "x2p", "x2pa", "ft", "fta", "orb", "drb", "trb", "ast", "stl", "blk", "tov", "pf", "pts"):
            totals[key] = totals.get(key, 0) + _number(row, key) * weight
    totals["position"] = next((row.get("pos") for row in sorted(rows, key=lambda r: int(r["season"]), reverse=True) if row.get("pos")), "")
    totals["seasons"] = tuple(sorted((int(row["season"]) for row in rows), reverse=True))
    return totals


def _divide(a, b):
    return a / b if b else 0.0


def _metric(data, name):
    if name in data:
        return data[name]
    mp, fga = data["mp"], data["fga"]
    metrics = {
        "pts_per36": _divide(data["pts"] * 36, mp), "fga_per36": _divide(fga * 36, mp),
        "ast_per36": _divide(data["ast"] * 36, mp), "tov_per36": _divide(data["tov"] * 36, mp),
        "trb_per36": _divide(data["trb"] * 36, mp), "orb_per36": _divide(data["orb"] * 36, mp),
        "drb_per36": _divide(data["drb"] * 36, mp), "stl_per36": _divide(data["stl"] * 36, mp),
        "blk_per36": _divide(data["blk"] * 36, mp), "pf_per36": _divide(data["pf"] * 36, mp),
        "effective_fg": _divide(data["fg"] + .5 * data["x3p"], fga),
        "true_shooting": _divide(data["pts"], 2 * (fga + .44 * data["fta"])),
        "three_pct": _divide(data["x3p"], data["x3pa"]), "two_pct": _divide(data["x2p"], data["x2pa"]),
        "ft_pct": _divide(data["ft"], data["fta"]), "ast_tov": _divide(data["ast"], data["tov"]),
        "three_attempt_rate": _divide(data["x3pa"], fga), "free_throw_rate": _divide(data["fta"], fga),
    }
    return metrics[name]


def _sample(data, name):
    if name in data:
        return data[name]
    return {"minutes": data["mp"], "shooting_possessions": data["fga"] + .44 * data["fta"],
            "fga": data["fga"], "x3pa": data["x3pa"], "x2pa": data["x2pa"], "fta": data["fta"],
            "decisions": data["ast"] + data["tov"]}[name]


def _percentile(value, cohort, inverse=False):
    if not cohort: return .5
    percentile = sum(candidate <= value for candidate in cohort) / len(cohort)
    return 1 - percentile if inverse else percentile


def _tier(rating):
    if rating >= 90: return "elite"
    if rating >= 85: return "excellent"
    if rating >= 80: return "great"
    if rating >= 75: return "good"
    if rating >= 70: return "above-average"
    if rating >= 65: return "average"
    if rating >= 55: return "below-average"
    if rating >= 45: return "poor"
    return "major-weakness"


def _ordinal(value):
    value = int(value)
    suffix = "th" if 10 < value % 100 < 14 else {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def _confidence_label(confidence, sample, minimum):
    if sample == 0: return "Insufficient Sample"
    if sample < minimum * .15: return "Insufficient Sample"
    if confidence >= 75: return "High"
    if confidence >= 50: return "Medium"
    if confidence > 0: return "Low"
    return "Unavailable"


@lru_cache(maxsize=1)
def _player_features():
    grouped = {}
    for row in _canonical_rows():
        grouped.setdefault(row["player_id"], []).append(row)
    features = {player_id: _blend(rows) for player_id, rows in grouped.items()}
    for player_id, event in nba_event_features.snapshot().get("players", {}).items():
        if player_id not in features:
            continue
        derived = {key: value for key, value in event.get("features", {}).items() if value is not None}
        counts = event.get("counts", {})
        derived["shot_fg"] = counts.get("shot_fg", 0)
        derived["shot_fga"] = counts.get("shot_fga", 0)
        derived["midrange_rate"] = (derived.get("short_midrange_fga", 0) + derived.get("long_midrange_fga", 0)) / derived["shot_fga"] if derived["shot_fga"] else None
        features[player_id].update({key: value for key, value in derived.items() if value is not None})
    # Possession rows use ESPN player ids; only verified identity links are merged.
    for espn_id, stats_id in _identity().items():
        possession = nba_possession_service.features_for_player(espn_id)
        if stats_id not in features or not possession: continue
        derived = {f"pos_{key}": value for key, value in possession.get("features", {}).items() if value is not None}
        derived.update({f"pos_{key}": value for key, value in possession.get("counts", {}).items()})
        features[stats_id].update(derived)
    return features


def _calculate(data, definition, all_features):
    if (definition.metric not in data and definition.metric not in DERIVED_BOX_METRICS) or \
            (definition.sample_metric not in data and definition.sample_metric not in BOX_SAMPLES):
        return None
    observed = _metric(data, definition.metric)
    sample = _sample(data, definition.sample_metric)
    league = [_metric(item, definition.metric) for item in all_features
              if (definition.metric in item or definition.metric in DERIVED_BOX_METRICS)
              and (definition.sample_metric in item or definition.sample_metric in BOX_SAMPLES)
              and _sample(item, definition.sample_metric) > 0]
    position = _primary_position(data["position"])
    position_values = [_metric(item, definition.metric) for item in all_features
                       if (definition.metric in item or definition.metric in DERIVED_BOX_METRICS)
                       and (definition.sample_metric in item or definition.sample_metric in BOX_SAMPLES)
                       and _sample(item, definition.sample_metric) > 0 and _primary_position(item["position"]) == position]
    league_percentile = _percentile(observed, league, definition.inverse)
    position_percentile = _percentile(observed, position_values, definition.inverse)
    reliability = min(1.0, sample / definition.sample_target)
    if sample == 0 and definition.zero_usage_is_low:
        adjusted = 0.0
    elif sample == 0:
        return None
    else:
        adjusted = reliability * league_percentile + (1 - reliability) * .5
        if definition.low_usage_threshold and sample < definition.low_usage_threshold:
            adjusted *= (sample / definition.low_usage_threshold) ** .5
    rating = round(RATING_MIN + adjusted * (RATING_MAX - RATING_MIN))
    confidence = round(reliability * definition.source_confidence * 100)
    sample_units = {"minutes": "minutes", "shooting_possessions": "shooting possessions",
                    "fga": "field-goal attempts", "x3pa": "3-point attempts",
                    "x2pa": "2-point attempts", "fta": "free-throw attempts", "decisions": "decisions",
                    "rim_fga": "rim attempts", "paint_fga": "paint attempts", "layup_fga": "layup attempts",
                    "dunk_fga": "dunk attempts", "floater_fga": "floater attempts",
                    "short_midrange_fga": "short-midrange attempts", "long_midrange_fga": "long-midrange attempts",
                    "corner_three_fga": "corner-three attempts", "above_break_three_fga": "above-break attempts",
                    "hook_fga": "hook-shot attempts",
                    "shot_fg": "made field goals", "shot_fga": "shot attempts"}
    league_rank, position_rank = round(league_percentile * 100), round(position_percentile * 100)
    is_rate = definition.metric.endswith("_rate")
    return {"id": definition.id, "name": definition.name, "category": definition.category,
            "rating": rating, "tier": _tier(rating), "confidence": confidence,
            "confidence_label": _confidence_label(confidence, sample, definition.sample_target),
            "description": definition.description, "observed": round(observed, 3),
            "observed_label": f"{observed * 100:.1f}%" if is_rate else f"{observed:.3f}",
            "sample": round(sample), "sample_label": f"{round(sample):,} {sample_units.get(definition.sample_metric, definition.sample_metric.removeprefix('pos_').replace('_', ' '))}",
            "league_percentile": league_rank, "league_percentile_label": _ordinal(league_rank),
            "position_percentile": position_rank, "position_percentile_label": _ordinal(position_rank), "reliability": round(reliability * 100),
            "feature": definition.metric, "reference_population": REFERENCE_POPULATION,
            "model_version": MODEL_VERSION, "fallback_used": definition.source.startswith("SportsDataverse"),
            "source": definition.source, "provenance": "possession-derived" if definition.source == "Derived Possession Evidence" else "event-derived" if definition.source.startswith("SportsDataverse") else "box-score-derived",
            "evidence_tier": "Derived Open-Data Possession Evidence" if definition.source == "Derived Possession Evidence" else "Direct Open-Data Event Evidence" if definition.source.startswith("SportsDataverse") else "Box-Score Evidence"}


def _summaries(granular):
    by_id = {item["id"]: item for item in granular}
    summaries = []
    for summary_id, name, children in SUMMARY_DEFINITIONS:
        available = [(by_id[child], weight) for child, weight in children if child in by_id and by_id[child]["confidence"] >= 20]
        if not available: continue
        total = sum(weight * max(.25, item["reliability"] / 100) for item, weight in available)
        rating = round(sum(item["rating"] * weight * max(.25, item["reliability"] / 100) for item, weight in available) / total)
        confidence = round(sum(item["confidence"] * weight for item, weight in available) / sum(weight for _, weight in available))
        summaries.append({"id": summary_id, "name": name, "rating": rating, "tier": _tier(rating),
                          "confidence": confidence, "confidence_label": _confidence_label(confidence, 1, 1),
                          "description": "League-wide weighted rollup of: " + ", ".join(item["name"] for item, _ in available) + ".",
                          "children": tuple(item["id"] for item, _ in available)})
    return tuple(summaries)


def _categories(granular):
    return tuple({"id": name.casefold().replace(" / ", "-").replace(" ", "-"), "name": name,
                  "description": description, "attributes": tuple(item for item in granular if item["category"] == name),
                  "status": "available" if any(item["category"] == name for item in granular) else "not-tracked"}
                 for name, description in CATEGORY_DESCRIPTIONS.items())


def _strengths_and_weaknesses(granular):
    eligible = [item for item in granular if item["confidence"] >= 45]
    return (tuple(sorted((item for item in eligible if item["rating"] >= 75), key=lambda x: x["rating"], reverse=True)[:5]),
            tuple(sorted((item for item in eligible if item["rating"] < 55), key=lambda x: x["rating"])[:5]))


def position_metadata_for_player(espn_player_id, fallback=""):
    """Canonical five-position metadata from the latest verified stats identity."""
    stats_id = _identity().get(str(espn_player_id))
    data = _player_features().get(stats_id, {})
    primary = str(data.get("position") or "").upper()
    if primary not in {"PG", "SG", "SF", "PF", "C"}:
        primary = str(fallback or "").upper()
    broad = _primary_position(primary)
    return {"primary_position": primary or broad, "secondary_position": None,
            "broad_position": broad, "position_source": "verified season statistics" if stats_id and data.get("position") else "ESPN roster fallback",
            "position_confidence": "High" if stats_id and data.get("position") else "Medium"}


@lru_cache(maxsize=1024)
def attributes_for_player(espn_player_id):
    stats_id = _identity().get(str(espn_player_id))
    data = _player_features().get(stats_id)
    if data is None: return None
    population = tuple(_player_features().values())
    granular = tuple(filter(None, (_calculate(data, item, population) for item in ATTRIBUTE_DEFINITIONS)))
    tendencies = tuple(filter(None, (_calculate(data, item, population) for item in TENDENCY_DEFINITIONS)))
    strengths, weaknesses = _strengths_and_weaknesses(granular)
    official_status = nba_official_features.snapshot().get("status", "not_loaded")
    event_snapshot = nba_event_features.snapshot()
    official_data = nba_official_features.features_for_player(stats_id)
    possession_data = nba_possession_service.features_for_player(str(espn_player_id))
    possession_features = possession_data.get("features", {})
    impact_labels = (("on_court_ortg","On-Court ORtg"),("on_court_drtg","On-Court DRtg"),
                     ("off_court_ortg","Off-Court ORtg"),("off_court_drtg","Off-Court DRtg"),
                     ("offensive_on_off","Offensive On/Off"),("defensive_on_off","Defensive On/Off"))
    impact = tuple({"id":key,"name":label,"value":possession_features[key],"source":"Contextual Impact Evidence"}
                   for key,label in impact_labels if possession_features.get(key) is not None)
    role_context = {"role":possession_features.get("role_context","Unknown"),
                    "creation_burden":possession_features.get("creation_burden"),
                    "offensive_possessions":possession_data.get("counts",{}).get("offensive_possessions",0)}
    return {"model_version": MODEL_VERSION, "season": MODEL_SEASON, "games": round(data["g"]),
            "source_seasons": data["seasons"], "calculated_at": datetime.now(timezone.utc).isoformat(),
            "reference_population": REFERENCE_POPULATION, "attributes": _summaries(granular),
            "granular_attributes": granular, "categories": _categories(granular), "tendencies": tendencies,
            "impact": impact, "role_context": role_context,
            "strengths": strengths, "weaknesses": weaknesses, "official_data_status": official_status,
            "event_data_status": event_snapshot.get("status", "not_loaded"),
            "event_coverage": event_snapshot.get("coverage", {}),
            "possession_data_status": nba_possession_service.snapshot().get("status", "not_loaded"),
            "possession_coverage": nba_possession_service.snapshot().get("coverage", {}),
            "official_source_count": len(official_data.get("seasons", {})) if official_data else 0,
            "data_note": "Ratings use an NBA-wide, three-season true-talent model. Position percentile is context only. "
                         + (" Validated hoopR shot events are included." if event_snapshot.get("status") == "verified" else " Shot-event data is not loaded.")
                         + (" Possession-derived context is included." if nba_possession_service.snapshot().get("status") == "verified" else " Possession context is not loaded.")
                         + (" Official NBA tracking data is included." if official_data else " Official tracking-only skills remain Not tracked.")}


def clear_caches():
    _stats.cache_clear(); _identity.cache_clear(); _player_features.cache_clear(); attributes_for_player.cache_clear(); nba_official_features.clear_cache(); nba_event_features.clear_cache(); nba_possession_service.clear_cache()
