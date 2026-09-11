"""Persistent, deterministic single-season NBA franchise simulation."""

from datetime import datetime, timezone
from functools import lru_cache
import json
import os
from pathlib import Path
from random import Random
import tempfile
import time
from uuid import uuid4

import nba_franchise_service as franchise
import nba_overall_service
import nba_overall_benchmark


SAVE_VERSION = 1
SAVE_DIR = Path(os.environ.get("NBA_FRANCHISE_SAVE_DIR",
                               Path(__file__).with_name("data") / "nba_franchise_saves"))


def _now():
    return datetime.now(timezone.utc).isoformat()


def _save_path(save_id):
    if not save_id or not str(save_id).replace("-", "").isalnum():
        raise ValueError("invalid franchise save ID")
    return SAVE_DIR / f"{save_id}.json"


def _write(data):
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    target = _save_path(data["id"])
    handle, temporary = tempfile.mkstemp(prefix="nba-save-", suffix=".json", dir=SAVE_DIR)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, separators=(",", ":"), allow_nan=False)
        for attempt in range(5):
            try:
                os.replace(temporary, target)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(.025 * (attempt + 1))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def create(team_code):
    team_code = str(team_code).upper()
    if team_code not in franchise.TEAM_BY_CODE:
        raise ValueError("unknown NBA team")
    timestamp = _now()
    data = {"version": SAVE_VERSION, "id": str(uuid4()), "season": franchise.RULES_SEASON,
            "team": team_code, "created_at": timestamp, "updated_at": timestamp,
            "results": [], "player_teams": {}, "pick_owners": {}, "transactions": []}
    _write(data)
    return data


def load(save_id):
    try:
        with _save_path(save_id).open(encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    if (data.get("version") != SAVE_VERSION or data.get("team") not in franchise.TEAM_BY_CODE
            or not isinstance(data.get("results"), list)):
        return None
    data.setdefault("player_teams", {})
    data.setdefault("pick_owners", {})
    data.setdefault("transactions", [])
    return data


def delete(save_id):
    """Delete one validated franchise save; never accept a broad filesystem target."""
    path = _save_path(save_id)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def roster_for_save(save, team_code):
    players = []
    moves = save.get("player_teams", {}) if save else {}
    for original_team in franchise.TEAMS:
        for player in franchise.roster(original_team.code):
            if moves.get(player["player_id"], original_team.code) == team_code:
                players.append(player)
    return tuple(sorted(players, key=lambda player: (player["position"], player["name"])))


def team_strength(team_code, save=None):
    """Build a team profile from calibrated talent and rotation-weighted skills."""
    players = []
    for player in roster_for_save(save, team_code) if save else franchise.roster(team_code):
        profile = player.get("attribute_profile")
        if not profile:
            continue
        ratings = {item["id"]: item["rating"] for item in profile["attributes"]}
        overall = player_overall(profile, player.get("position", "F"), player.get("name"))
        if overall is None:
            continue
        offense = (ratings.get("scoring", 50) * .45 + ratings.get("playmaking", 50) * .25
                   + ratings.get("finishing", 50) * .20 + ratings.get("rebounding", 50) * .10)
        defense = (ratings.get("steal_hands", 50) * .38 + ratings.get("rim_protection", 50) * .37
                   + ratings.get("rebounding", 50) * .25)
        players.append({"overall": overall, "offense": offense, "defense": defense})
    players.sort(key=lambda item: item["overall"], reverse=True)
    rotation = players[:10]
    if not rotation:
        return {"overall": 50.0, "offense": 50.0, "defense": 50.0}

    # Starters drive results; the sixth through tenth players still reward depth
    # without carrying the same weight as the primary lineup.
    rotation_weights = (1.00, .92, .84, .77, .70, .46, .38, .31, .25, .20)[:len(rotation)]

    def weighted(key):
        return sum(player[key] * weight for player, weight in zip(rotation, rotation_weights)) / sum(rotation_weights)

    talent = weighted("overall")
    offense = talent * .62 + weighted("offense") * .38
    defense = talent * .62 + weighted("defense") * .38
    team_overall = talent * .72 + offense * .16 + defense * .12
    return {"overall": round(team_overall, 1),
            "offense": round(offense, 1), "defense": round(defense, 1)}


def player_overall(profile, position="F", player_name=None):
    """Convert calibrated summary attributes into one transparent scouting grade."""
    modeled = nba_overall_service.calculate(profile, position)
    return nba_overall_benchmark.calibrated_overall(player_name, modeled) if player_name else modeled


@lru_cache(maxsize=1)
def _league_players():
    players, seen = [], set()
    for team in franchise.TEAMS:
        for player in franchise.roster(team.code):
            if player["player_id"] in seen or not player.get("attribute_profile"):
                continue
            seen.add(player["player_id"])
            overall = player_overall(player["attribute_profile"], player["position"], player["name"])
            if overall is not None:
                players.append({"player_id": player["player_id"], "name": player["name"],
                                "position": player["position"], "team": team.code,
                                "overall": overall})
    players.sort(key=lambda item: (-item["overall"], item["name"]))
    return tuple({**player, "rank": rank} for rank, player in enumerate(players, 1))


def player_rankings(query="", limit=100):
    query = " ".join(str(query).casefold().split())
    rows = _league_players()
    if query:
        rows = tuple(player for player in rows if query in player["name"].casefold())
    return rows[:limit]


@lru_cache(maxsize=1)
def team_rankings():
    rows = [{"team": team, **team_strength(team.code)} for team in franchise.TEAMS]
    rows.sort(key=lambda item: (-item["overall"], item["team"].city))
    return tuple({**row, "rank": rank} for rank, row in enumerate(rows, 1))


def _player_quality(player):
    profile = player.get("attribute_profile") or {}
    overall = player_overall(profile, player.get("position", "F"), player.get("name"))
    return overall or 50


def _allocate(total, weights, randomizer):
    """Allocate an integer team total while preserving the exact final sum."""
    adjusted = [max(.01, weight * randomizer.uniform(.86, 1.14)) for weight in weights]
    denominator = sum(adjusted)
    raw = [total * weight / denominator for weight in adjusted]
    values = [int(value) for value in raw]
    for index in sorted(range(len(raw)), key=lambda item: raw[item] - values[item], reverse=True)[:total - sum(values)]:
        values[index] += 1
    return values


def _simulate_team_box_score(team_code, score, randomizer, players=None):
    roster = sorted(players if players is not None else franchise.roster(team_code),
                    key=lambda player: (-_player_quality(player), player["name"]))[:10]
    if not roster:
        return []
    qualities = [_player_quality(player) for player in roster]
    minutes = _allocate(240, [quality ** 2.15 for quality in qualities], randomizer)
    points = _allocate(score, [quality ** 3 for quality in qualities], randomizer)
    rebounds = _allocate(max(32, round(randomizer.gauss(44, 4))),
                         [(_player_quality(player) ** 1.5) * (1.28 if player.get("broad_position", player["position"]) == "C" else 1.12 if player.get("broad_position", player["position"]) == "F" else .82) for player in roster], randomizer)
    assists = _allocate(max(17, round(randomizer.gauss(27, 4))),
                        [(_player_quality(player) ** 1.6) * (1.3 if player.get("broad_position", player["position"]) == "G" else .85) for player in roster], randomizer)
    steals = _allocate(max(3, round(randomizer.gauss(8, 2))), qualities, randomizer)
    blocks = _allocate(max(2, round(randomizer.gauss(5, 2))),
                       [quality * (1.55 if player.get("broad_position", player["position"]) == "C" else 1.15 if player.get("broad_position", player["position"]) == "F" else .55) for quality, player in zip(qualities, roster)], randomizer)
    turnovers = _allocate(max(7, round(randomizer.gauss(13, 2))), qualities, randomizer)
    lines = []
    for index, player in enumerate(roster):
        three_made = min(points[index] // 3, max(0, round(points[index] * randomizer.uniform(.08, .18))))
        field_goals = max(0, round((points[index] - three_made * 3) / 2 * randomizer.uniform(.72, .9))) + three_made
        attempts = field_goals + max(1, round(field_goals * randomizer.uniform(.72, 1.2)))
        lines.append({"player_id": player["player_id"], "name": player["name"],
                      "position": player["position"], "min": minutes[index], "pts": points[index],
                      "reb": rebounds[index], "ast": assists[index], "stl": steals[index],
                      "blk": blocks[index], "tov": turnovers[index], "fgm": field_goals,
                      "fga": attempts, "x3pm": three_made})
    return lines


def _simulate_game(save, game):
    user_code, opponent_code = save["team"], game["opponent"]
    user, opponent = team_strength(user_code, save), team_strength(opponent_code, save)
    randomizer = Random(f"{save['id']}:{save['season']}:{game['game']}")
    home_edge = 2.4 if game["home"] else -2.4
    user_expected = 113.5 + (user["offense"] - 50) * .24 - (opponent["defense"] - 50) * .18 + home_edge
    opponent_expected = 113.5 + (opponent["offense"] - 50) * .24 - (user["defense"] - 50) * .18
    user_score = max(75, round(randomizer.gauss(user_expected, 10.5)))
    opponent_score = max(75, round(randomizer.gauss(opponent_expected, 10.5)))
    overtime = False
    while user_score == opponent_score:
        overtime = True
        user_score += randomizer.randint(5, 13)
        opponent_score += randomizer.randint(5, 13)
    box_score = {user_code: _simulate_team_box_score_for_save(save, user_code, user_score, randomizer),
                 opponent_code: _simulate_team_box_score_for_save(save, opponent_code, opponent_score, randomizer)}
    return {"game": game["game"], "opponent": opponent_code, "home": game["home"],
            "team_score": user_score, "opponent_score": opponent_score,
            "result": "W" if user_score > opponent_score else "L", "overtime": overtime,
            "box_score": box_score, "simulated_at": _now(), "engine": "roster-attributes-v2"}


def game_result(save, game_number):
    return next((result for result in save.get("results", ()) if result.get("game") == game_number), None)


def simulated_player_stats(save, team_code=None):
    """Aggregate persisted box scores for one team across the simulated season."""
    team_code = team_code or save["team"]
    totals = {}
    for result in save.get("results", ()):
        lines = result.get("box_score", {}).get(team_code, ())
        for line in lines:
            row = totals.setdefault(line["player_id"], {"player_id": line["player_id"],
                                "name": line["name"], "position": line["position"], "gp": 0,
                                "min": 0, "pts": 0, "reb": 0, "ast": 0, "stl": 0,
                                "blk": 0, "tov": 0, "fgm": 0, "fga": 0, "x3pm": 0})
            row["gp"] += 1
            for key in ("min", "pts", "reb", "ast", "stl", "blk", "tov", "fgm", "fga", "x3pm"):
                row[key] += line.get(key, 0)
    rows = []
    for row in totals.values():
        games = row["gp"] or 1
        per_game = {key: round(row[key] / games, 1) for key in ("min", "pts", "reb", "ast", "stl", "blk", "tov", "x3pm")}
        rows.append({**row, "per_game": per_game,
                     "fg_pct": round(row["fgm"] / row["fga"] * 100, 1) if row["fga"] else 0})
    return tuple(sorted(rows, key=lambda row: (-row["pts"], row["name"])))


def simulate(save, count=1):
    count = max(1, min(int(count), 7))
    schedule = franchise.regular_season_schedule(save["team"])
    completed = {result["game"] for result in save["results"]}
    pending = [game for game in schedule if game["game"] not in completed][:count]
    for game in pending:
        save["results"].append(_simulate_game(save, game))
        _maybe_cpu_trade(save, game["game"])
    save["results"].sort(key=lambda result: result["game"])
    save["updated_at"] = _now()
    _write(save)
    return save


def season_state(save):
    schedule = franchise.regular_season_schedule(save["team"])
    by_game = {result["game"]: result for result in save["results"]}
    annotated = tuple({**game, "result": by_game.get(game["game"])} for game in schedule)
    wins = sum(result["result"] == "W" for result in save["results"])
    losses = len(save["results"]) - wins
    next_game = next((game for game in annotated if game["result"] is None), None)
    start = len(save["results"])
    current_week = annotated[start:start + 4]
    simulated_stats = simulated_player_stats(save)
    return {"franchise_save": save, "schedule": annotated, "current_week": current_week,
            "recent_results": tuple(reversed(save["results"][-5:])), "wins": wins, "losses": losses,
            "games_played": len(save["results"]), "games_remaining": 82 - len(save["results"]),
            "next_game": next_game, "season_complete": len(save["results"]) == 82,
            "team_strength": team_strength(save["team"], save), "simulated_stats": simulated_stats,
            "simulated_stats_preview": simulated_stats[:5]}


def _simulate_team_box_score_for_save(save, team_code, score, randomizer):
    return _simulate_team_box_score(team_code, score, randomizer, roster_for_save(save, team_code))


def draft_picks(save, team_code):
    picks = []
    owners = save.get("pick_owners", {})
    for original in franchise.TEAMS:
        for year in range(2027, 2031):
            for round_number in (1, 2):
                pick_id = f"{year}-{round_number}-{original.code}"
                if owners.get(pick_id, original.code) == team_code:
                    picks.append({"id": pick_id, "year": year, "round": round_number,
                                  "original_team": original.code,
                                  "label": f"{year} Round {round_number} · {original.code}"})
    return tuple(picks)


def starting_lineup_for_save(save, team_code):
    ranked = sorted(roster_for_save(save, team_code),
                    key=lambda player: (_player_quality(player), player["salary"] or 0), reverse=True)
    lineup, used = [], set()
    for label, position in (("PG", "G"), ("SG", "G"), ("SF", "F"), ("PF", "F"), ("C", "C")):
        player = next((item for item in ranked if item.get("broad_position", item["position"]) == position and item["player_id"] not in used), None)
        player = player or next((item for item in ranked if item["player_id"] not in used), None)
        if player:
            used.add(player["player_id"])
            lineup.append({"slot": label, "name": player["name"]})
    return tuple(lineup)


def _asset_value(player=None, pick=None):
    if player:
        overall = _player_quality(player)
        age = player.get("age") or 28
        return max(8, (overall - 45) * 2.4 + max(0, 29 - age) * 1.6)
    return 42 if pick and pick["round"] == 1 else 16


def propose_trade(save, partner_code, user_player_ids=(), cpu_player_ids=(), user_pick_ids=(), cpu_pick_ids=()):
    user_code = save["team"]
    if partner_code not in franchise.TEAM_BY_CODE or partner_code == user_code:
        return {"status": "declined", "message": "Choose another NBA team."}
    user_players = {player["player_id"]: player for player in roster_for_save(save, user_code)}
    cpu_players = {player["player_id"]: player for player in roster_for_save(save, partner_code)}
    user_picks = {pick["id"]: pick for pick in draft_picks(save, user_code)}
    cpu_picks = {pick["id"]: pick for pick in draft_picks(save, partner_code)}
    def normalize(values):
        if isinstance(values, str):
            values = (values,)
        return tuple(dict.fromkeys(value for value in values if value))
    user_player_ids, cpu_player_ids = normalize(user_player_ids), normalize(cpu_player_ids)
    user_pick_ids, cpu_pick_ids = normalize(user_pick_ids), normalize(cpu_pick_ids)
    outgoing = tuple(user_players[player_id] for player_id in user_player_ids if player_id in user_players)
    incoming = tuple(cpu_players[player_id] for player_id in cpu_player_ids if player_id in cpu_players)
    outgoing_picks = tuple(user_picks[pick_id] for pick_id in user_pick_ids if pick_id in user_picks)
    incoming_picks = tuple(cpu_picks[pick_id] for pick_id in cpu_pick_ids if pick_id in cpu_picks)
    save["last_trade_offer"] = {"partner": partner_code, "user_players": list(user_player_ids),
                                "cpu_players": list(cpu_player_ids), "user_picks": list(user_pick_ids),
                                "cpu_picks": list(cpu_pick_ids)}
    if not (outgoing or outgoing_picks) or not (incoming or incoming_picks):
        return {"status": "declined", "message": "Each team must include at least one valid asset."}
    cpu_receives = sum(_asset_value(player=player) for player in outgoing) + sum(_asset_value(pick=pick) for pick in outgoing_picks)
    cpu_sends = sum(_asset_value(player=player) for player in incoming) + sum(_asset_value(pick=pick) for pick in incoming_picks)
    ratio = cpu_receives / max(cpu_sends, 1)
    if ratio < .78:
        response = {"status": "declined", "message": "The CPU declined. The value is too far apart to negotiate."}
    elif ratio < .96:
        needed = "an additional first-round pick" if ratio < .87 else "an additional second-round pick"
        response = {"status": "counter", "message": f"The CPU is interested, but counters by asking for {needed}."}
    else:
        for player in outgoing:
            save["player_teams"][player["player_id"]] = partner_code
        for player in incoming:
            save["player_teams"][player["player_id"]] = user_code
        for pick in outgoing_picks:
            save["pick_owners"][pick["id"]] = partner_code
        for pick in incoming_picks:
            save["pick_owners"][pick["id"]] = user_code
        sent = ", ".join([player["name"] for player in outgoing] + [pick["label"] for pick in outgoing_picks])
        received = ", ".join([player["name"] for player in incoming] + [pick["label"] for pick in incoming_picks])
        transaction = {"type": "Trade", "game": len(save["results"]), "title": f"{user_code} and {partner_code} complete a trade",
                       "detail": f"{user_code} acquired {received}; {partner_code} acquired {sent}."}
        save["transactions"].insert(0, transaction)
        save["last_trade_offer"] = {"partner": partner_code, "user_players": [], "cpu_players": [],
                                    "user_picks": [], "cpu_picks": []}
        response = {"status": "accepted", "message": "Trade accepted. Rosters and asset ownership have been updated."}
    save["last_trade_response"] = response
    save["updated_at"] = _now()
    _write(save)
    return response


def _maybe_cpu_trade(save, game_number):
    if game_number % 9:
        return
    randomizer = Random(f"cpu-trade:{save['id']}:{game_number}")
    teams = [team.code for team in franchise.TEAMS if team.code != save["team"]]
    first, second = randomizer.sample(teams, 2)
    first_roster = sorted(roster_for_save(save, first), key=_player_quality)[:10]
    second_roster = sorted(roster_for_save(save, second), key=_player_quality)[:10]
    if not first_roster or not second_roster:
        return
    player_a, player_b = min(((a, b) for a in first_roster for b in second_roster),
                             key=lambda pair: abs(_asset_value(pair[0]) - _asset_value(pair[1])))
    save["player_teams"][player_a["player_id"]] = second
    save["player_teams"][player_b["player_id"]] = first
    save["transactions"].insert(0, {"type": "League trade", "game": game_number,
        "title": f"{first} and {second} complete a trade",
        "detail": f"{first} acquired {player_b['name']}; {second} acquired {player_a['name']}."})
