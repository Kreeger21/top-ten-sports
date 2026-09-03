from functools import lru_cache
import json
from pathlib import Path


DATA_PATH = Path(__file__).with_name("data") / "team_logo_rosters.json"
NFL_SLOTS = ("QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE")
NBA_SLOTS = ("PG", "SG", "SF", "PF", "C")


@lru_cache(maxsize=1)
def _data():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def teams(sport):
    return {key: value["name"] for key, value in _data()[sport].items()}


def _clue(slot, player):
    return {
        "position": slot, "name": player["name"], "college": player["college"],
        "college_logo": player["college_logo"],
    }


@lru_cache(maxsize=128)
def get_clues(sport, team_key):
    team = _data()[sport][team_key]
    players = team["players"]
    if sport == "nfl":
        by_id = {player["id"]: player for player in players}
        clues, used = [], set()
        for slot in NFL_SLOTS:
            source = slot.rstrip("12") if slot.startswith("RB") else slot
            choices = team["depth"].get(source, [])
            player = next((by_id[player_id] for player_id in choices
                           if player_id in by_id and player_id not in used), None)
            if player:
                used.add(player["id"])
                clues.append(_clue(slot, player))
        return tuple(clues)

    chosen, used = [], set()
    groups = (("PG", "G"), ("SG", "G"), ("SF", "F"), ("PF", "F"), ("C", "C"))
    for slot, position in groups:
        player = next((item for item in players if item["position"] == position and item["id"] not in used), None)
        if not player:
            player = next((item for item in players if item["id"] not in used), None)
        if player:
            used.add(player["id"])
            chosen.append(_clue(slot, player))
    return tuple(chosen)
