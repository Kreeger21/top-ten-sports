"""Build a consolidated 1950-present NFL career-game snapshot."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "nfl_career_history.csv"
OFFENSE_URL = "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv"
DEFENSE_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_{year}.csv"
STATS = ["passing_yards", "passing_tds", "rushing_yards", "rushing_tds",
         "receiving_yards", "receiving_tds", "tackles", "def_sacks", "def_interceptions"]
KEYS = ["season", "player_id", "player_display_name", "recent_team", "position"]


def normalized(frame):
    frame = frame.copy()
    for column in STATS:
        if column not in frame:
            frame[column] = 0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return frame[KEYS + STATS]


def defense_year(year):
    columns = ["player_id", "player_display_name", "position", "recent_team", "season",
               "def_tackles_solo", "def_tackles_with_assist", "def_sacks", "def_interceptions"]
    data = pd.read_csv(DEFENSE_URL.format(year=year), usecols=columns)
    data["tackles"] = pd.to_numeric(data["def_tackles_solo"], errors="coerce").fillna(0) + pd.to_numeric(
        data["def_tackles_with_assist"], errors="coerce").fillna(0)
    return normalized(data)


def main():
    old_offense = pd.read_csv(ROOT / "data" / "nfl_offense_history.csv").rename(columns={"field_position": "position"})
    old_defense = pd.read_csv(ROOT / "data" / "nfl_defense_history.csv")
    modern_offense = pd.read_csv(OFFENSE_URL, low_memory=False)
    modern_offense = modern_offense.loc[modern_offense["season_type"] == "REG"]
    with ThreadPoolExecutor(max_workers=8) as executor:
        modern_defense = pd.concat(executor.map(defense_year, range(1999, 2026)), ignore_index=True)
    data = pd.concat([normalized(old_offense), normalized(old_defense), normalized(modern_offense), modern_defense], ignore_index=True)
    data = data.groupby(KEYS, as_index=False, dropna=False)[STATS].sum()
    data.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(data):,} NFL player-team seasons to {OUTPUT}")


if __name__ == "__main__":
    main()
