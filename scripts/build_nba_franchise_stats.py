"""Build the multi-season player feature source used by NBA Franchise Mode."""

from pathlib import Path

import pandas as pd


SOURCE = "https://raw.githubusercontent.com/cmuchina3/nba-stats-1947-present-curated/main/data/raw/Player_Totals.csv"
OUTPUT = Path(__file__).resolve().parents[1] / "data" / "nba_franchise_stats_2025.csv"
COLUMNS = [
    "season", "player", "player_id", "age", "team", "pos", "g", "gs", "mp",
    "fg", "fga", "fg_percent", "x3p", "x3pa", "x3p_percent", "x2p", "x2pa",
    "x2p_percent", "e_fg_percent", "ft", "fta", "ft_percent", "orb", "drb",
    "trb", "ast", "stl", "blk", "tov", "pf", "pts", "trp_dbl",
]


def main():
    data = pd.read_csv(SOURCE, usecols=COLUMNS)
    data = data.loc[(data["season"].between(2023, 2025)) & (data["team"].str.fullmatch(r"[A-Z]{3}"))]
    data.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(data):,} completed-season player records to {OUTPUT}")


if __name__ == "__main__":
    main()
