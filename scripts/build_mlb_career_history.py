"""Build a compact MLB batting and pitching career-game snapshot from Lahman."""
from pathlib import Path

import pandas as pd


BASE = "https://raw.githubusercontent.com/vincentarelbundock/Rdatasets/master/csv/Lahman/"
OUTPUT = Path(__file__).resolve().parents[1] / "data" / "mlb_career_history.csv"


def main():
    batting = pd.read_csv(BASE + "Batting.csv")
    pitching = pd.read_csv(BASE + "Pitching.csv")
    people = pd.read_csv(BASE + "People.csv", usecols=["playerID", "nameFirst", "nameLast"])
    people["player"] = people[["nameFirst", "nameLast"]].fillna("").agg(" ".join, axis=1).str.strip()
    batting = batting.groupby(["playerID", "yearID", "teamID"], as_index=False).agg(
        games=("G", "max"), hits=("H", "sum"), home_runs=("HR", "sum"),
        rbi=("RBI", "sum"), stolen_bases=("SB", "sum"),
    )
    pitching = pitching.groupby(["playerID", "yearID", "teamID"], as_index=False).agg(
        pitching_games=("G", "max"), wins=("W", "sum"), strikeouts=("SO", "sum"),
        saves=("SV", "sum"), innings_outs=("IPouts", "sum"),
    )
    data = batting.merge(pitching, on=["playerID", "yearID", "teamID"], how="outer")
    data["games"] = data[["games", "pitching_games"]].max(axis=1)
    data["innings_pitched"] = data["innings_outs"] / 3
    data = data.merge(people[["playerID", "player"]], on="playerID", how="left")
    data = data.rename(columns={"playerID": "player_id", "yearID": "season", "teamID": "team"})
    columns = ["season", "player_id", "player", "team", "games", "hits", "home_runs", "rbi",
               "stolen_bases", "wins", "strikeouts", "saves", "innings_pitched"]
    data[columns].to_csv(OUTPUT, index=False)
    print(f"Wrote {len(data):,} MLB player-team seasons to {OUTPUT}")


if __name__ == "__main__":
    main()
