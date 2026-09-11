"""Canonical NBA possession evidence shared by hoopR and pbpstats pipelines.

This module deliberately stores observable events, classifications and confidence
separately.  Nothing produced here is labelled as optical NBA Tracking data.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from functools import lru_cache
from pathlib import Path
import re
from typing import Any, Iterable

MODEL_VERSION = "v1-possession-context"
DATA_PATH = Path(__file__).with_name("data") / "nba_possession_features.json"
POSSESSION_PATH = Path(__file__).with_name("data") / "nba_possessions.jsonl.gz"
SEASON_WEIGHTS = {2025: 1.0, 2024: .65, 2023: .40}

POST_PATTERNS = {
    "hook": re.compile(r"\b(?:jump |running )?hook\b", re.I),
    "turnaround_fadeaway": re.compile(r"\bturnaround fadeaway\b", re.I),
    "turnaround": re.compile(r"\bturnaround\b", re.I),
    "fadeaway": re.compile(r"\bfadeaway\b", re.I),
    "post_layup": re.compile(r"\bpost(?:erized)? layup\b", re.I),
    "post_dunk": re.compile(r"\bpost dunk\b", re.I),
}


@dataclass
class Provenance:
    source: str
    underlying_data_source: str
    season: int
    game_id: str
    derivation_method: str
    sample_size: int = 1
    confidence: str = "Medium"
    evidence_tier: str = "Direct Open-Data Possession Evidence"
    model_version: str = MODEL_VERSION


@dataclass
class CanonicalPossession:
    game_id: str
    season: int
    possession_id: str
    period: int
    start_time: float | None
    end_time: float | None
    duration: float | None
    offensive_team: str
    defensive_team: str
    offensive_players: list[str] = field(default_factory=list)
    defensive_players: list[str] = field(default_factory=list)
    possession_start_type: str = "Other"
    possession_end_type: str = "Other"
    events: list[dict[str, Any]] = field(default_factory=list)
    shot_attempt: bool = False
    shot_player: str | None = None
    shot_location: str | None = None
    shot_result: str | None = None
    assist_player: str | None = None
    turnover_player: str | None = None
    steal_player: str | None = None
    offensive_rebound: str | None = None
    defensive_rebound: str | None = None
    foul: bool = False
    free_throws: int = 0
    points: int = 0
    transition_class: str = "Unknown"
    transition_confidence: float = 0.0
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def classify_start(previous: dict[str, Any] | None, first: dict[str, Any] | None = None) -> str:
    previous = previous or {}
    first = first or {}
    kind = str(previous.get("event_type") or previous.get("type") or "").casefold()
    text = f"{previous.get('text', '')} {first.get('text', '')}".casefold()
    if previous.get("steal_player") or "steal" in kind or "steal" in text:
        return "Steal"
    if previous.get("turnover_player") or "turnover" in kind:
        return "Turnover"
    if previous.get("defensive_rebound") or ("rebound" in kind and "defensive" in text):
        return "Defensive Rebound"
    if previous.get("made") or ("made" in text and "free throw" not in text):
        return "Made Basket"
    if "jump ball" in kind or "jump ball" in text:
        return "Jump Ball"
    if "period" in kind or "start of" in text:
        return "Start of Period"
    if previous.get("dead_ball") or "dead ball" in text:
        return "Dead Ball"
    return "Other"


def classify_end(events: Iterable[dict[str, Any]]) -> str:
    events = list(events)
    if not events:
        return "Other"
    if any(e.get("turnover_player") or str(e.get("event_type", "")).casefold() == "turnover" for e in events):
        return "Turnover"
    if any(e.get("free_throw") for e in events):
        return "Free Throws"
    shots = [e for e in events if e.get("shot_attempt")]
    if shots and shots[-1].get("made"):
        return "Made FG"
    if shots:
        after = events[events.index(shots[-1]) + 1:]
        if any(e.get("offensive_rebound") for e in after):
            return "Missed FG + offensive rebound"
        if any(e.get("defensive_rebound") for e in after):
            return "Missed FG + defensive rebound"
    if any("end of" in str(e.get("text", "")).casefold() for e in events):
        return "End of Period"
    return "Other"


def classify_transition(start_type: str, duration: float | None, events: Iterable[dict[str, Any]]) -> tuple[str, float]:
    """Multi-signal transition classifier; ambiguity remains Unknown."""
    events = list(events)
    live_start = start_type in {"Steal", "Turnover", "Defensive Rebound"}
    explicit = any(e.get("fast_break") or "fast break" in str(e.get("text", "")).casefold() for e in events)
    early_shot = duration is not None and duration <= 7 and any(e.get("shot_attempt") for e in events)
    short = duration is not None and duration <= 10
    steal_start = start_type == "Steal"
    score = (.50 if explicit else 0) + (.20 if live_start else 0) + (.25 if steal_start else 0) + \
            (.15 if early_shot else 0) + (.05 if short else 0) + \
            (.10 if any(e.get("made") for e in events) else 0)
    if score >= .70:
        return "High Confidence Transition", round(score, 2)
    if score >= .35:
        return "Likely Transition", round(score, 2)
    if start_type == "Made Basket" and duration is not None and duration >= 10:
        return "Half Court", .85
    if not live_start and duration is not None and duration >= 12:
        return "Half Court", .75
    return "Unknown", round(score, 2)


def classify_post_action(text: str) -> str | None:
    for action, pattern in POST_PATTERNS.items():
        if pattern.search(text or ""):
            return action
    return None


def finalize_possession(possession: CanonicalPossession) -> CanonicalPossession:
    possession.possession_end_type = classify_end(possession.events)
    possession.transition_class, possession.transition_confidence = classify_transition(
        possession.possession_start_type, possession.duration, possession.events
    )
    return possession


def _clock_seconds(value) -> float | None:
    try:
        minutes, seconds = str(value).split(":", 1)
        return int(minutes) * 60 + float(seconds)
    except (TypeError, ValueError):
        return None


def from_pbpstats(possession, season: int) -> CanonicalPossession:
    """Adapt a real :mod:`pbpstats` Possession without depending on private loaders."""
    # Imports stay local so stored snapshots remain readable without the optional package.
    from pbpstats.resources.enhanced_pbp import FieldGoal, Foul, FreeThrow, Rebound, Turnover

    events = []
    first = possession.events[0]
    offense = str(possession.offense_team_id)
    teams = [str(team) for team in first.current_players]
    defense = next((team for team in teams if team != offense), "")
    for event in possession.events:
        item = {"event_type": type(event).__name__, "text": str(getattr(event, "description", "")),
                "team_id": str(getattr(event, "team_id", ""))}
        if isinstance(event, FieldGoal):
            item.update(shot_attempt=True, shot_player=str(event.player1_id), made=event.is_made,
                        points=int(getattr(event, "shot_value", 2)),
                        assist_player=str(event.player2_id) if event.is_assisted else None)
        elif isinstance(event, Turnover) and not event.is_no_turnover:
            item["turnover_player"] = str(getattr(event, "player1_id", "")) or None
            item["steal_player"] = str(getattr(event, "player3_id", "")) if event.is_steal else None
        elif isinstance(event, Rebound) and event.is_real_rebound:
            item["offensive_rebound" if event.oreb else "defensive_rebound"] = str(event.player1_id) or None
        elif isinstance(event, FreeThrow): item["free_throw"] = True
        elif isinstance(event, Foul): item["foul"] = True
        events.append(item)
    start = _clock_seconds(possession.start_time); end = _clock_seconds(possession.end_time)
    lineups = first.current_players
    result = CanonicalPossession(game_id=str(possession.game_id), season=int(season),
        possession_id=f"{possession.game_id}:{possession.period}:{getattr(possession, 'number', 0)}",
        period=int(possession.period), start_time=start, end_time=end,
        duration=max(0, start-end) if start is not None and end is not None else None,
        offensive_team=offense, defensive_team=defense,
        offensive_players=[str(x) for x in lineups.get(int(possession.offense_team_id), lineups.get(possession.offense_team_id, []))],
        defensive_players=[str(x) for x in lineups.get(int(defense), lineups.get(defense, []))] if defense else [],
        possession_start_type=str(possession.possession_start_type), events=events,
        points=sum(int(e.get("points", 0)) for e in events if e.get("made")),
        provenance=asdict(Provenance(source="pbpstats", underlying_data_source="stats.nba.com/data.nba.com",
            season=int(season), game_id=str(possession.game_id), derivation_method="pbpstats Possession adapter")))
    shot = next((e for e in reversed(events) if e.get("shot_attempt")), None)
    if shot:
        result.shot_attempt=True; result.shot_player=shot.get("shot_player")
        result.shot_result="made" if shot.get("made") else "missed"; result.assist_player=shot.get("assist_player")
    turnover = next((e for e in events if e.get("turnover_player")), None)
    rebound = next((e for e in reversed(events) if e.get("offensive_rebound") or e.get("defensive_rebound")), None)
    if turnover: result.turnover_player=turnover.get("turnover_player"); result.steal_player=turnover.get("steal_player")
    if rebound: result.offensive_rebound=rebound.get("offensive_rebound"); result.defensive_rebound=rebound.get("defensive_rebound")
    result.foul=any(e.get("foul") for e in events); result.free_throws=sum(bool(e.get("free_throw")) for e in events)
    return finalize_possession(result)


def second_chance_actions(possession: CanonicalPossession) -> list[dict[str, Any]]:
    """Actions after an offensive rebound within the same possession."""
    found = False
    actions = []
    for event in possession.events:
        if event.get("offensive_rebound"):
            found = True
            continue
        if found and (event.get("shot_attempt") or event.get("turnover_player") or event.get("foul")):
            actions.append(event)
    return actions


def aggregate_player_possessions(possessions: Iterable[CanonicalPossession], season_weights=None) -> dict[str, Any]:
    """Aggregate numerators/denominators; percentages are calculated only afterward."""
    weights = season_weights or SEASON_WEIGHTS
    players: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    seasons: dict[str, set[int]] = defaultdict(set)
    games: dict[str, set[str]] = defaultdict(set)
    player_teams: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    team_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    player_sources: dict[str, set[str]] = defaultdict(set)
    underlying_sources: dict[str, set[str]] = defaultdict(set)
    for p in possessions:
        weight = weights.get(p.season, 1.0)
        lineup_valid = len(set(p.offensive_players)) == 5 and len(set(p.defensive_players)) == 5
        offense = set(p.offensive_players) if lineup_valid else set()
        defense = set(p.defensive_players) if lineup_valid else set()
        if lineup_valid:
            team_totals[p.offensive_team]["offensive_possessions"] += weight
            team_totals[p.offensive_team]["points"] += p.points * weight
            team_totals[p.defensive_team]["defensive_possessions"] += weight
            team_totals[p.defensive_team]["opponent_points"] += p.points * weight
        for player in offense:
            players[player]["offensive_possessions"] += weight
            players[player]["team_points_on"] += p.points * weight
            seasons[player].add(p.season); games[player].add(p.game_id)
            player_teams[player][p.offensive_team] += weight
        for player in defense:
            players[player]["defensive_possessions"] += weight
            players[player]["opponent_points_on"] += p.points * weight
            seasons[player].add(p.season); games[player].add(p.game_id)
            player_teams[player][p.defensive_team] += weight
        transition_weight = p.transition_confidence if "Transition" in p.transition_class else 0
        involved = {p.shot_player, p.assist_player, p.turnover_player} - {None}
        evidenced_players=offense|defense|involved|({p.offensive_rebound,p.defensive_rebound}-{None})
        for player in evidenced_players:
            player_sources[player].add(str(p.provenance.get("source","unknown")))
            underlying_sources[player].add(str(p.provenance.get("underlying_data_source","unknown")))
        for player in involved:
            players[player]["creation_events"] += weight
        if p.shot_player:
            c = players[p.shot_player]; c["possessions_finished"] += weight; c["fga"] += weight
            if p.shot_result == "made":
                c["fgm"] += weight
                if p.assist_player: c["assisted_fgm"] += weight
                else: c["unassisted_fgm"] += weight
            if transition_weight:
                c["transition_possessions"] += weight * transition_weight
                c["transition_fga"] += weight * transition_weight
                c["transition_points"] += p.points * weight * transition_weight
            action = next((classify_post_action(str(e.get("text", ""))) for e in p.events if e.get("shot_player") == p.shot_player), None)
            if action:
                c["post_actions"] += weight; c["post_fga"] += weight
                if p.shot_result == "made": c["post_fgm"] += weight
        if p.assist_player:
            players[p.assist_player]["assists"] += weight
            if transition_weight: players[p.assist_player]["transition_assists"] += weight * transition_weight
        if p.turnover_player:
            players[p.turnover_player]["turnovers"] += weight
            players[p.turnover_player]["possessions_finished"] += weight
            if transition_weight: players[p.turnover_player]["transition_turnovers"] += weight * transition_weight
        if p.offensive_rebound:
            players[p.offensive_rebound]["offensive_rebounds"] += weight
        for action in second_chance_actions(p):
            actor = action.get("shot_player") or action.get("turnover_player")
            if actor: players[actor]["second_chance_actions"] += weight
            if actor and action.get("made"): players[actor]["second_chance_points"] += float(action.get("points", 2)) * weight
    result = {}
    for player, raw in players.items():
        c = dict(raw); off = c.get("offensive_possessions", 0); creation = c.get("creation_events", 0)
        rate = lambda key, den: round(100 * c.get(key, 0) / den, 3) if den else None
        primary_team=max(player_teams[player],key=player_teams[player].get) if player_teams[player] else None
        team=team_totals.get(primary_team,{}) if primary_team else {}
        off_pos=max(0,team.get("offensive_possessions",0)-off); def_pos=max(0,team.get("defensive_possessions",0)-c.get("defensive_possessions",0))
        on_ortg=round(100*c.get("team_points_on",0)/off,2) if off else None
        on_drtg=round(100*c.get("opponent_points_on",0)/c.get("defensive_possessions",1),2) if c.get("defensive_possessions") else None
        off_ortg=round(100*(team.get("points",0)-c.get("team_points_on",0))/off_pos,2) if off_pos else None
        off_drtg=round(100*(team.get("opponent_points",0)-c.get("opponent_points_on",0))/def_pos,2) if def_pos else None
        features = {
            "creation_burden": rate("creation_events", off),
            "possessions_finished_per_100": rate("possessions_finished", off),
            "shots_per_100": rate("fga", off), "turnovers_per_100": rate("turnovers", off),
            "assists_per_100": rate("assists", off),
            "passing_security": round(c.get("assists",0)/(c.get("assists",0)+c.get("turnovers",0)),5) if c.get("assists",0)+c.get("turnovers",0) else None,
            "self_created_makes_per_100": rate("unassisted_fgm", off),
            "assisted_makes_per_100": rate("assisted_fgm", off),
            "unassisted_make_rate": round(c.get("unassisted_fgm", 0) / c.get("fgm", 1), 5) if c.get("fgm") else None,
            "assisted_make_rate": round(c.get("assisted_fgm", 0) / c.get("fgm", 1), 5) if c.get("fgm") else None,
            "unassisted_make_rate": round(c.get("unassisted_fgm", 0) / c.get("fgm", 1), 5) if c.get("fgm") else None,
            "turnovers_per_100_creation": rate("turnovers", creation),
            "handle_security": round(1-c.get("turnovers",0)/creation,5) if creation else None,
            "transition_frequency": round(c.get("transition_possessions", 0) / off, 5) if off else None,
            "transition_points_per_possession": round(c.get("transition_points", 0) / c.get("transition_possessions", 1), 4) if c.get("transition_possessions") else None,
            "post_tendency": round(c.get("post_actions", 0) / off, 5) if off else None,
            "post_efficiency": round(c.get("post_fgm", 0) / c.get("post_fga", 1), 5) if c.get("post_fga") else None,
            "second_chance_points_per_action": round(c.get("second_chance_points", 0) / c.get("second_chance_actions", 1), 4) if c.get("second_chance_actions") else None,
            "on_court_ortg": on_ortg, "on_court_drtg": on_drtg,
            "off_court_ortg": off_ortg, "off_court_drtg": off_drtg,
            "offensive_on_off": round(on_ortg-off_ortg,2) if on_ortg is not None and off_ortg is not None else None,
            "defensive_on_off": round(off_drtg-on_drtg,2) if on_drtg is not None and off_drtg is not None else None,
        }
        result[player] = {"seasons": sorted(seasons[player], reverse=True), "games": len(games[player]), "primary_team":primary_team,
            "counts": {k: round(v, 3) for k, v in c.items()}, "features": features,
            "provenance": {"source":" + ".join(sorted(player_sources[player])),"underlying_data_source":" + ".join(sorted(underlying_sources[player])),
                "derivation_method":"canonical possession aggregation","sample_size":round(off),
                "confidence":"High" if off >= 1500 else "Medium" if off >= 500 else "Low",
                "evidence_tier":"Derived Possession Evidence","model_version":MODEL_VERSION}}
    burdens=sorted(item["features"]["creation_burden"] for item in result.values() if item["features"]["creation_burden"] is not None)
    if burdens:
        median=burdens[len(burdens)//2]; upper=burdens[int(len(burdens)*.75)]
        for item in result.values():
            burden=item["features"]["creation_burden"]
            if burden is None: role="Unknown"
            elif burden>=upper: role="Primary Creator"
            elif burden>=median: role="Secondary Creator"
            elif (item["features"].get("assisted_make_rate") or 0)>=.70: role="Finisher / Off-Ball Scorer"
            else: role="Low-Usage Specialist"
            item["features"]["role_context"]=role
            item["features"]["role_thresholds"]={"league_median_creation_burden":median,"upper_quartile_creation_burden":upper}
    return result


@lru_cache(maxsize=1)
def snapshot():
    if not DATA_PATH.exists(): return {"status":"not_loaded","players":{},"coverage":{}}
    try:
        with DATA_PATH.open(encoding="utf-8") as handle: data = json.load(handle)
        if not isinstance(data.get("players"), dict): raise ValueError
        return data
    except (OSError, ValueError, TypeError):
        return {"status":"invalid","players":{},"coverage":{}}


def features_for_player(player_id):
    return snapshot().get("players", {}).get(str(player_id), {})


def payload(possessions: Iterable[CanonicalPossession]):
    possessions = list(possessions); players = aggregate_player_possessions(possessions)
    return {"status":"verified","schema_version":1,"model_version":MODEL_VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),"players":players,
        "coverage":{"games":len({p.game_id for p in possessions}),"possessions":len(possessions),
                    "players":len(players),"source":"pbpstats + NBA play-by-play"}}


def clear_cache(): snapshot.cache_clear()
