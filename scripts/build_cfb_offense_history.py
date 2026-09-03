"""Build position-aware CFB offense totals for Fill the Field.

Uses official ESPN player box-score totals and the matching season roster
release from SportsDataverse. Output is compact and checked in so production
does not rely on large live downloads.
"""
from pathlib import Path

import pandas as pd


RELEASE_ROOT = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
OUTPUT = Path(__file__).resolve().parents[1] / "data" / "cfb_offense_history.csv"
TEAMS_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "cfb_offense_teams.txt"
SEASONS = range(2004, 2026)
BOX_COLUMNS = [
    "season", "team_id", "athlete_id", "athlete_name", "category",
    "passingYards", "passingTouchdowns", "rushingYards", "rushingTouchdowns",
    "receivingYards", "receivingTouchdowns",
]
ROSTER_COLUMNS = [
    "team_id", "athlete_id", "division", "position_abbreviation", "team_short_display_name",
]
STAT_RENAMES = {
    "passingYards": "passing_yards", "passingTouchdowns": "passing_tds",
    "rushingYards": "rushing_yards", "rushingTouchdowns": "rushing_tds",
    "receivingYards": "receiving_yards", "receivingTouchdowns": "receiving_tds",
}


def season_data(season):
    box_url = f"{RELEASE_ROOT}/espn_cfb_player_box/player_box_{season}.csv"
    roster_url = f"{RELEASE_ROOT}/espn_cfb_rosters/cfb_rosters_{season}.csv.gz"
    box = pd.read_csv(box_url, usecols=BOX_COLUMNS, low_memory=False)
    roster = pd.read_csv(roster_url, usecols=ROSTER_COLUMNS, low_memory=False)
    roster = roster.loc[roster["division"].str.casefold() == "fbs"].drop_duplicates(
        ["team_id", "athlete_id"]
    )
    data = box.loc[box["category"].isin({"passing", "rushing", "receiving"})].merge(
        roster, on=["team_id", "athlete_id"], how="inner"
    )
    for source, target in STAT_RENAMES.items():
        data[target] = pd.to_numeric(data[source], errors="coerce").fillna(0)
    data["field_position"] = data["position_abbreviation"].replace({
        "HB": "RB", "FB": "RB", "TB": "RB", "H-B": "RB",
    })
    stats = list(STAT_RENAMES.values())
    data = data.loc[data["field_position"].isin({"QB", "RB", "WR", "TE"})]
    data = data.groupby(
        ["season", "athlete_id", "athlete_name", "team_short_display_name", "field_position"],
        as_index=False,
    )[stats].sum().rename(columns={
        "athlete_id": "player_id", "athlete_name": "player", "team_short_display_name": "team",
    })
    teams = sorted(set(roster["team_short_display_name"].dropna()))
    return data, teams


def main():
    seasons, teams_2025 = [], []
    for season in SEASONS:
        print(f"Loading ESPN box scores and rosters for {season}...", flush=True)
        frame, teams = season_data(season)
        seasons.append(frame)
        if season == 2025:
            teams_2025 = teams
    pd.concat(seasons, ignore_index=True).to_csv(OUTPUT, index=False)
    TEAMS_OUTPUT.write_text("\n".join(teams_2025) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} and {len(teams_2025)} current FBS teams", flush=True)


if __name__ == "__main__":
    main()
