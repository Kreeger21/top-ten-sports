from functools import lru_cache
import json
from pathlib import Path


DATA_PATH = Path(__file__).with_name("data") / "team_logo_rosters.json"
NFL_OFFENSE_SLOTS = ("QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "LT", "LG", "C", "RG", "RT")
NFL_DEFENSE_SLOTS = ("DL1", "DL2", "DL3", "DL4", "LB1", "LB2", "LB3", "CB1", "CB2", "S1", "S2")
NBA_SLOTS = ("PG", "SG", "SF", "PF", "C")


@lru_cache(maxsize=1)
def _data():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def teams(sport):
    return {key: value["name"] for key, value in _data()[sport].items()}


def _clue(slot, player):
    college_logo = player.get("college_logo")
    return {
        "position": slot, "name": player["name"],
        "college": player["college"] if college_logo else "International",
        "college_logo": college_logo,
    }


@lru_cache(maxsize=128)
def get_clues(sport, team_key, side="offense"):
    team = _data()[sport][team_key]
    players = team["players"]
    if sport == "nfl":
        by_id = {player["id"]: player for player in players}
        clues, used = [], set()
        slots = NFL_DEFENSE_SLOTS if side == "defense" else NFL_OFFENSE_SLOTS
        for slot in slots:
            source = slot.rstrip("12") if slot.startswith("RB") else slot
            choices = team["depth"].get(source, [])
            player = next((by_id[player_id] for player_id in choices
                           if player_id in by_id and player_id not in used), None)
            if not player and side == "defense":
                group = slot.rstrip("1234")
                eligible_positions = {
                    "DL": {"DE", "DT", "NT", "EDGE", "DL"},
                    "LB": {"LB", "ILB", "MLB", "OLB"},
                    "CB": {"CB"}, "S": {"S", "FS", "SS"},
                }[group]
                player = next((item for item in players
                               if item["position"] in eligible_positions and item["id"] not in used), None)
            if player:
                used.add(player["id"])
                clues.append(_clue(slot, player))
        return tuple(clues)

    chosen, used = [], set()
    by_id = {player["id"]: player for player in players}
    groups = (
        ("PG", {"G"}), ("SG", {"G"}), ("SF", {"G", "F"}),
        ("PF", {"F", "C"}), ("C", {"C"}),
    )
    for slot, eligible_positions in groups:
        player = next((by_id[player_id] for player_id in team["depth"].get(slot, [])
                       if player_id in by_id and player_id not in used
                       and by_id[player_id]["position"] in eligible_positions), None)
        if not player:
            player = next((item for item in players
                           if item["position"] in eligible_positions and item["id"] not in used), None)
        if not player:
            player = next((item for item in players if item["id"] not in used), None)
        if player:
            used.add(player["id"])
            chosen.append(_clue(slot, player))
    return tuple(chosen)
