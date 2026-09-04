"""Build compact NBA player accolades from Basketball Reference-derived data."""
from pathlib import Path

import pandas as pd


BASE = "https://raw.githubusercontent.com/cmuchina3/nba-stats-1947-present-curated/main/data/raw/"
OUTPUT = Path(__file__).resolve().parents[1] / "data" / "nba_player_accolades.csv"
AWARD_LABELS = {
    "aba mvp": "ABA MVP", "aba roy": "ABA Rookie of the Year",
    "baa roy": "BAA Rookie of the Year", "nba clutch_poy": "Clutch Player of the Year",
    "nba dpoy": "Defensive Player of the Year", "nba mip": "Most Improved Player",
    "nba mvp": "NBA MVP", "nba roy": "Rookie of the Year",
    "nba smoy": "Sixth Man of the Year",
}
ALL_STARS_2025 = {
    "Giannis Antetokounmpo", "Jayson Tatum", "Karl-Anthony Towns", "Jalen Brunson",
    "Donovan Mitchell", "Jaylen Brown", "Damian Lillard", "Darius Garland", "Tyler Herro",
    "Cade Cunningham", "Evan Mobley", "Pascal Siakam", "Trae Young", "Nikola Jokić",
    "Kevin Durant", "LeBron James", "Stephen Curry", "Shai Gilgeous-Alexander",
    "Anthony Edwards", "Anthony Davis", "James Harden", "Jaren Jackson Jr.",
    "Alperen Şengün", "Jalen Williams", "Victor Wembanyama", "Kyrie Irving",
}
AWARDS_2025 = {
    "Shai Gilgeous-Alexander": "NBA MVP",
    "Evan Mobley": "Defensive Player of the Year",
    "Stephon Castle": "Rookie of the Year",
    "Dyson Daniels": "Most Improved Player",
    "Payton Pritchard": "Sixth Man of the Year",
    "Jalen Brunson": "Clutch Player of the Year",
}


def main():
    all_stars = pd.read_csv(BASE + "All-Star%20Selections.csv")
    teams = pd.read_csv(BASE + "End%20of%20Season%20Teams.csv")
    awards = pd.read_csv(BASE + "Player%20Award%20Shares.csv")
    records = {}
    totals = pd.read_csv(OUTPUT.with_name("nba_court_history.csv"), usecols=["player", "player_id"])
    ids_by_name = dict(totals.drop_duplicates("player").set_index("player")["player_id"])

    def record(player_id, season):
        return records.setdefault((str(player_id), int(season)), {"all_star": False, "accolades": []})

    for row in all_stars.itertuples():
        record(row.player_id, row.season)["all_star"] = True
    for row in teams.itertuples():
        label = f"{row.type} {row.number_tm} Team"
        record(row.player_id, row.season)["accolades"].append(label)
    winners = awards.loc[awards["winner"].astype(str).str.upper() == "TRUE"]
    for row in winners.itertuples():
        label = AWARD_LABELS.get(row.award, str(row.award).upper())
        record(row.player_id, row.season)["accolades"].append(label)
    for name in ALL_STARS_2025:
        if name in ids_by_name:
            record(ids_by_name[name], 2025)["all_star"] = True
    for name, label in AWARDS_2025.items():
        if name in ids_by_name:
            record(ids_by_name[name], 2025)["accolades"].append(label)

    rows = []
    for (player_id, season), values in sorted(records.items(), key=lambda item: (item[0][1], item[0][0])):
        rows.append({
            "season": season, "player_id": player_id,
            "all_star": values["all_star"],
            "accolades": "|".join(dict.fromkeys(values["accolades"])),
        })
    pd.DataFrame(rows).to_csv(OUTPUT, index=False)
    print(f"Wrote {len(rows):,} accolade seasons to {OUTPUT}")


if __name__ == "__main__":
    main()
