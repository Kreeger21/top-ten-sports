"""Build the compact NBA Fill the Court regular-season data file.

Source: the public-domain NBA/ABA/BAA dataset compiled from Basketball Reference
and curated at https://github.com/cmuchina3/nba-stats-1947-present-curated.
"""
from pathlib import Path

import pandas as pd


SOURCE = "https://raw.githubusercontent.com/cmuchina3/nba-stats-1947-present-curated/main/data/raw/Player_Totals.csv"
OUTPUT = Path(__file__).resolve().parents[1] / "data" / "nba_court_history.csv"
COLUMNS = ["season", "player", "player_id", "team", "pos", "pts", "trb", "ast", "stl", "blk", "x3p"]


def main():
    data = pd.read_csv(SOURCE, usecols=COLUMNS)
    data = data.loc[(data["season"].between(1950, 2025)) & (data["team"].str.fullmatch(r"[A-Z]{3}"))]
    data.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(data):,} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
