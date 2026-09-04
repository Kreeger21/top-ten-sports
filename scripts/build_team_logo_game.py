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
COUNTRY_FLAGS = {
    "Australia": "🇦🇺", "Bosnia & Herzegovina": "🇧🇦", "Brazil": "🇧🇷", "Canada": "🇨🇦",
    "Croatia": "🇭🇷", "Czech Republic": "🇨🇿", "France": "🇫🇷", "Georgia": "🇬🇪",
    "Germany": "🇩🇪", "Greece": "🇬🇷", "Israel": "🇮🇱", "Italy": "🇮🇹", "Latvia": "🇱🇻",
    "Mexico": "🇲🇽", "Russia": "🇷🇺", "Senegal": "🇸🇳", "Serbia": "🇷🇸", "Slovenia": "🇸🇮",
    "Spain": "🇪🇸", "Switzerland": "🇨🇭", "Trinidad & Tobago": "🇹🇹", "T�rkiye": "🇹🇷",
    "Türkiye": "🇹🇷", "USA": "🇺🇸",
}
COUNTRY_CODES = {
    "Australia": "au", "Bosnia & Herzegovina": "ba", "Brazil": "br", "Canada": "ca",
    "Croatia": "hr", "Czech Republic": "cz", "France": "fr", "Georgia": "ge",
    "Germany": "de", "Greece": "gr", "Israel": "il", "Italy": "it", "Latvia": "lv",
    "Mexico": "mx", "Russia": "ru", "Senegal": "sn", "Serbia": "rs", "Slovenia": "si",
    "Spain": "es", "Switzerland": "ch", "Trinidad & Tobago": "tt", "T�rkiye": "tr",
    "Türkiye": "tr", "USA": "us",
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
        if not position:
            continue
        country = (player.get("birthPlace") or {}).get("country") or "Unknown"
        college_name = college.get("shortName") or college.get("name")
        players.append({
            "id": player.get("id"), "name": player.get("displayName"), "position": position,
            "college": college_name or "International",
            "college_logo": logos[0].get("href") if logos else None,
            "country_flag": None if logos else COUNTRY_FLAGS.get(country, "🌐"),
            "country": None if logos else country,
            "country_code": None if logos else COUNTRY_CODES.get(country),
        })
    return players


def nfl_depth(team_id):
    url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/depthcharts"
    payload = requests.get(url, timeout=30).json()
    groups = payload.get("depthchart", [])
    offense = next((group for group in groups if "WR" in group.get("name", "")), {})
    defense = next((group for group in groups if group.get("name", "").startswith("Base")), {})
    positions = {**offense.get("positions", {}), **defense.get("positions", {})}
    sources = {
        "QB": "qb", "RB": "rb", "WR1": "wr1", "WR2": "wr2", "WR3": "wr3", "TE": "te",
        "LT": "lt", "LG": "lg", "C": "c", "RG": "rg", "RT": "rt",
        "CB1": "lcb", "CB2": "rcb", "S1": "ss", "S2": "fs",
    }
    if "3-4" in defense.get("name", ""):
        sources.update({
            "DL1": "lde", "DL2": "nt", "DL3": "rde", "DL4": "wlb",
            "LB1": "lilb", "LB2": "rilb", "LB3": "slb",
        })
    else:
        sources.update({
            "DL1": "lde", "DL2": "ldt", "DL3": "rdt", "DL4": "rde",
            "LB1": "wlb", "LB2": "mlb", "LB3": "slb",
        })
    return {
        slot: [athlete.get("id") for athlete in positions.get(source, {}).get("athletes", [])]
        for slot, source in sources.items()
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
                "country_flag": None,
                "country": None,
                "country_code": None,
            })
    return players


def nba_depth(team_id):
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/depthcharts"
    payload = requests.get(url, timeout=30).json()
    chart = next(iter(payload.get("depthchart", [])), {})
    positions = chart.get("positions", {})
    return {
        slot: [athlete.get("id") for athlete in positions.get(slot.lower(), {}).get("athletes", [])]
        for slot in ("PG", "SG", "SF", "PF", "C")
    }


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
            depth = nfl_depth(team_id) if sport == "nfl" else nba_depth(team_id)
            players = roster(sport_path, team_id)
            if sport == "nfl" and not players:
                players = nfl_depth_players(depth)
            result[sport][team_key] = {"name": team_name, "players": players, "depth": depth}
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
