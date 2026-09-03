"""Build position-aware CFB defensive totals for Fill the Field."""
from pathlib import Path

import pandas as pd


RELEASE_ROOT = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
OUTPUT = Path(__file__).resolve().parents[1] / "data" / "cfb_defense_history.csv"
SEASONS = range(2004, 2026)
BOX_COLUMNS = [
    "season", "team_id", "athlete_id", "athlete_name", "category",
    "totalTackles", "sacks", "tacklesForLoss", "passesDefended", "interceptions",
]
ROSTER_COLUMNS = [
    "team_id", "athlete_id", "division", "position_abbreviation", "team_short_display_name",
]
STAT_RENAMES = {
    "totalTackles": "tackles", "sacks": "sacks", "tacklesForLoss": "tfl",
    "passesDefended": "passes_defended", "interceptions": "interceptions",
}
POSITION_GROUPS = {
    "DE": "DL", "DL": "DL", "DT": "DL", "NT": "DL", "EDGE": "DL",
    "LB": "LB", "CB": "CB", "S": "S", "DB": "DB",
}


def season_data(season):
    box_url = f"{RELEASE_ROOT}/espn_cfb_player_box/player_box_{season}.csv"
    roster_url = f"{RELEASE_ROOT}/espn_cfb_rosters/cfb_rosters_{season}.csv.gz"
    available = set(pd.read_csv(box_url, nrows=0).columns)
    box = pd.read_csv(box_url, usecols=[column for column in BOX_COLUMNS if column in available], low_memory=False)
    roster = pd.read_csv(roster_url, usecols=ROSTER_COLUMNS, low_memory=False)
    roster = roster.loc[roster["division"].str.casefold() == "fbs"].drop_duplicates(
        ["team_id", "athlete_id"]
    )
    data = box.loc[box["category"].isin({"defensive", "interceptions"})].merge(
        roster, on=["team_id", "athlete_id"], how="inner"
    )
    for source, target in STAT_RENAMES.items():
        data[target] = pd.to_numeric(data[source], errors="coerce").fillna(0) if source in data else 0
    data["field_group"] = data["position_abbreviation"].map(POSITION_GROUPS)
    data = data.loc[data["field_group"].notna()]
    stats = list(STAT_RENAMES.values())
    return data.groupby(
        ["season", "athlete_id", "athlete_name", "team_short_display_name", "field_group"],
        as_index=False,
    )[stats].sum().rename(columns={
        "athlete_id": "player_id", "athlete_name": "player", "team_short_display_name": "team",
    })


def main():
    seasons = []
    for season in SEASONS:
        print(f"Loading ESPN defensive box scores and rosters for {season}...", flush=True)
        seasons.append(season_data(season))
    pd.concat(seasons, ignore_index=True).to_csv(OUTPUT, index=False)
    print(f"Wrote {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
