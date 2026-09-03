"""Build the compact pre-nflverse defensive history used by Fill the Field.

Source game logs are the archived Sports Reference extract published at
https://www.kaggle.com/datasets/zynicide/nfl-football-player-stats. Historical
roster positions come from the nflverse roster CSV mirrors published by
https://myfootballtoolbox.com/nfl/rosters/downloads/.

This is a build-time utility. The web app reads only the generated CSV and does
not scrape either site at runtime.
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import ijson
import pandas as pd
import requests


FIRST_SEASON = 1982
LAST_SEASON = 1998
ROSTER_URL = "https://myfootballtoolbox.com/nfl/rosters/downloads/rosters_{year}.csv"
TEAM_CODES = {
    "GNB": "GB", "KAN": "KC", "NWE": "NE", "NOR": "NO", "SFO": "SF",
    "TAM": "TB", "SDG": "LAC", "RAI": "LV", "OAK": "LV", "RAM": "LAR",
}
DEFENSIVE_POSITIONS = {"DE", "DT", "NT", "DL", "LB", "ILB", "MLB", "OLB", "CB", "S", "FS", "SS", "SAF", "DB"}
# Sports Reference occasionally revises historical season records after an
# archive is published. Keep audited changes explicit and source-reviewable.
OFFICIAL_CORRECTIONS = {
    ("Robert Porcher", 1994, "DET"): {"def_sacks": 3.0},
}


def normalize_team(team, year):
    if team == "BAL" and year <= 1983:
        return "IND"
    if team == "HOU" and year <= 1996:
        return "TEN"
    if team == "STL":
        return "ARI" if year <= 1987 else "LAR"
    if team == "PHO":
        return "ARI"
    return TEAM_CODES.get(team, team)


def load_profiles(path):
    with path.open("rb") as source:
        return {
            int(row["player_id"]): (row["name"], str(row.get("position") or ""))
            for row in ijson.items(source, "item")
        }


def load_rosters(cache_dir):
    frames = []
    cache_dir.mkdir(parents=True, exist_ok=True)
    for year in range(FIRST_SEASON, LAST_SEASON + 1):
        path = cache_dir / f"rosters_{year}.csv"
        if not path.exists():
            response = requests.get(ROSTER_URL.format(year=year), timeout=30)
            response.raise_for_status()
            path.write_bytes(response.content)
        frame = pd.read_csv(path, usecols=["season", "team", "depth_chart_position", "full_name"])
        frame["team"] = [normalize_team(team, year) for team in frame["team"]]
        frames.append(frame)
    rosters = pd.concat(frames, ignore_index=True).drop_duplicates(["season", "team", "full_name"])
    return {
        (int(row.season), row.team, row.full_name): str(row.depth_chart_position)
        for row in rosters.itertuples(index=False)
    }


def build(games_path, profiles_path, roster_cache, output_path):
    profiles = load_profiles(profiles_path)
    rosters = load_rosters(roster_cache)
    totals = defaultdict(lambda: [0.0, 0.0, 0.0])
    with games_path.open("rb") as source:
        for row in ijson.items(source, "item"):
            year = int(row["year"])
            if year < FIRST_SEASON or year > LAST_SEASON:
                continue
            player_id = int(row["player_id"])
            team = normalize_team(row["team"], year)
            values = totals[(player_id, year, team)]
            values[0] += float(row.get("defense_sacks") or 0)
            values[1] += float(row.get("defense_tackles") or 0) + float(row.get("defense_tackle_assists") or 0)
            values[2] += float(row.get("defense_interceptions") or 0)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["player_id", "player_display_name", "position", "recent_team", "season",
                         "def_sacks", "tackles", "def_interceptions"])
        for (player_id, year, team), (sacks, tackles, interceptions) in sorted(totals.items()):
            name, profile_position = profiles[player_id]
            profile_parts = str(profile_position).upper().replace("/", "-").split("-")
            profile_tokens = set(profile_parts)
            position = profile_parts[0] if profile_parts else ""
            if not profile_tokens or profile_tokens == {"DB"}:
                position = rosters.get((year, team, name), profile_position)
            position_tokens = set(str(position).upper().replace("/", "-").split("-"))
            if not position_tokens.intersection(DEFENSIVE_POSITIONS):
                continue
            correction = OFFICIAL_CORRECTIONS.get((name, year, team), {})
            sacks = correction.get("def_sacks", sacks)
            writer.writerow([f"archive-{player_id}", name, position, team, year,
                             sacks, tackles if year >= 1994 else 0, interceptions if year >= 1994 else 0])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("games", type=Path)
    parser.add_argument("profiles", type=Path)
    parser.add_argument("--roster-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.games, args.profiles, args.roster_cache, args.output)
