"""Build the compact 1950–1998 offense history used by NFL Fill the Field.

The input files are the archived Sports Reference game logs and profiles from
https://www.kaggle.com/datasets/zynicide/nfl-football-player-stats. The web app
reads only the generated CSV; it never downloads this archive at runtime.
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import ijson


FIRST_SEASON = 1950
LAST_SEASON = 1998
AFL_1960_TEAMS = {"BUF", "BOS", "DAL", "DEN", "HOU", "LAC", "NYT", "OAK"}
TEAM_CODES = {
    "CHC": "ARI", "GNB": "GB", "KAN": "KC", "NWE": "NE", "NOR": "NO",
    "NYT": "NYJ", "SFO": "SF", "TAM": "TB", "SDG": "LAC", "RAI": "LV",
    "OAK": "LV", "RAM": "LAR", "PHO": "ARI",
}
POSITION_GROUPS = {
    "QB": {"QB"},
    "RB": {"RB", "HB", "FB", "B", "TB", "LH", "RH"},
    "WR": {"WR", "FL", "SE", "E"},
    "TE": {"TE"},
}


def normalize_team(team, year):
    if team == "BAL":
        return "IND" if 1953 <= year <= 1983 else team
    if team == "DTX":
        return "KC" if 1960 <= year <= 1962 else team
    if team == "HOU" and 1960 <= year <= 1996:
        return "TEN"
    if team == "STL":
        return "ARI" if year <= 1987 else "LAR"
    return TEAM_CODES.get(team, team)


def normalize_position(position):
    primary = str(position or "").upper().replace("/", "-").split("-")[0]
    for group, positions in POSITION_GROUPS.items():
        if primary in positions:
            return group
    return None


def regular_season_games(year, team):
    if year == 1982:
        return 9
    if year == 1987:
        return 15
    if year >= 1978:
        return 16
    if year >= 1961 or (year == 1960 and team in AFL_1960_TEAMS):
        return 14
    return 12


def load_profiles(path):
    with path.open("rb") as source:
        return {
            int(row["player_id"]): (str(row["name"]).strip(), normalize_position(row.get("position")))
            for row in ijson.items(source, "item")
        }


def build(games_path, profiles_path, output_path):
    profiles = load_profiles(profiles_path)
    totals = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    with games_path.open("rb") as source:
        for row in ijson.items(source, "item"):
            year = int(row["year"])
            if not FIRST_SEASON <= year <= LAST_SEASON:
                continue
            if int(row["game_number"]) > regular_season_games(year, row["team"]):
                continue
            player_id = int(row["player_id"])
            name, position = profiles.get(player_id, (None, None))
            if not name or not position:
                continue
            team = normalize_team(row["team"], year)
            values = totals[(player_id, name, position, team, year)]
            values[0] += int(row.get("passing_yards") or 0)
            values[1] += int(row.get("passing_touchdowns") or 0)
            values[2] += int(row.get("rushing_yards") or 0)
            values[3] += int(row.get("rushing_touchdowns") or 0)
            values[4] += int(row.get("receiving_yards") or 0)
            values[5] += int(row.get("receiving_touchdowns") or 0)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["player_id", "player_display_name", "field_position", "recent_team", "season",
                         "passing_yards", "passing_tds", "rushing_yards", "rushing_tds",
                         "receiving_yards", "receiving_tds"])
        for key, values in sorted(totals.items()):
            player_id, name, position, team, year = key
            writer.writerow([f"archive-{player_id}", name, position, team, year, *values])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("games", type=Path)
    parser.add_argument("profiles", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.games, args.profiles, args.output)
