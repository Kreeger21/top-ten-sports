"""Snapshot current ESPN NFL/NBA rosters and player college logos."""
import json
from pathlib import Path
import sys

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nba_court_service import TEAMS as NBA_TEAMS
from nfl_field_service import TEAMS as NFL_TEAMS


OUTPUT = Path(__file__).resolve().parents[1] / "data" / "team_logo_rosters.json"
SPORTS = {
    "nfl": ("football/nfl", NFL_TEAMS),
    "nba": ("basketball/nba", NBA_TEAMS),
}
ESPN_ABBREVIATIONS = {
    "nfl": {"WAS": "WSH"},
    "nba": {"GSW": "GS", "NOP": "NO", "NYK": "NY", "SAS": "SA", "UTA": "UTAH", "WAS": "WSH"},
}


def roster(sport_path, team_id):
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/teams/{team_id}/roster"
    payload = requests.get(url, timeout=30).json()
    athletes = payload.get("athletes", [])
    if athletes and "items" in athletes[0]:
        athletes = [player for group in athletes for player in group.get("items", [])]
    players = []
    for player in athletes:
        college = player.get("college") or {}
        logos = college.get("logos") or []
        position = (player.get("position") or {}).get("abbreviation")
        if not position or not logos:
            continue
        players.append({
            "id": player.get("id"), "name": player.get("displayName"), "position": position,
            "college": college.get("shortName") or college.get("name"),
            "college_logo": logos[0].get("href"),
        })
    return players


def nfl_depth(team_id):
    url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/depthcharts"
    payload = requests.get(url, timeout=30).json()
    offense = next((group for group in payload.get("depthchart", []) if "WR" in group.get("name", "")), {})
    positions = offense.get("positions", {})
    return {
        slot: [athlete.get("id") for athlete in positions.get(source, {}).get("athletes", [])]
        for slot, source in {
            "QB": "qb", "RB": "rb", "WR1": "wr1", "WR2": "wr2", "WR3": "wr3", "TE": "te",
        }.items()
    }


def nfl_depth_players(depth):
    players = []
    for player_id in dict.fromkeys(player_id for ids in depth.values() for player_id in ids):
        url = f"https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/{player_id}"
        athlete = requests.get(url, timeout=30).json().get("athlete", {})
        college = athlete.get("college") or {}
        position = (athlete.get("position") or {}).get("abbreviation")
        if college.get("id") and position:
            players.append({
                "id": player_id, "name": athlete.get("displayName"), "position": position,
                "college": college.get("shortName") or college.get("name"),
                "college_logo": f'https://a.espncdn.com/i/teamlogos/ncaa/500/{college["id"]}.png',
            })
    return players


def main():
    result = {}
    for sport, (sport_path, teams) in SPORTS.items():
        result[sport] = {}
        listing = requests.get(
            f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/teams?limit=100", timeout=30
        ).json()
        listed = [entry["team"] for entry in listing["sports"][0]["leagues"][0]["teams"]]
        ids = {team["abbreviation"]: team["id"] for team in listed}
        for team_key, (team_name, _) in teams.items():
            print(f"Loading {sport.upper()} roster: {team_name}", flush=True)
            espn_key = ESPN_ABBREVIATIONS.get(sport, {}).get(team_key, team_key)
            team_id = ids[espn_key]
            depth = nfl_depth(team_id) if sport == "nfl" else {}
            players = roster(sport_path, team_id)
            if sport == "nfl" and not players:
                players = nfl_depth_players(depth)
            result[sport][team_key] = {"name": team_name, "players": players, "depth": depth}
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
