from functools import lru_cache
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
from pybaseball import bwar_bat, bwar_pitch


APPEARANCES_URL = "https://raw.githubusercontent.com/vincentarelbundock/Rdatasets/master/csv/Lahman/Appearances.csv"

TEAMS = {
    "ARI": ("Arizona Diamondbacks", {"ARI"}), "ATH": ("Athletics", {"PHA", "KCA", "OAK", "ATH"}),
    "ATL": ("Atlanta Braves", {"BSN", "MLN", "ATL"}), "BAL": ("Baltimore Orioles", {"SLB", "BAL"}),
    "BOS": ("Boston Red Sox", {"BOS"}), "CHW": ("Chicago White Sox", {"CHW"}),
    "CHC": ("Chicago Cubs", {"CHC"}), "CIN": ("Cincinnati Reds", {"CIN"}),
    "CLE": ("Cleveland Guardians", {"CLE"}), "COL": ("Colorado Rockies", {"COL"}),
    "DET": ("Detroit Tigers", {"DET"}), "HOU": ("Houston Astros", {"HOU"}),
    "KCR": ("Kansas City Royals", {"KCR"}), "LAA": ("Los Angeles Angels", {"LAA", "CAL", "ANA"}),
    "LAD": ("Los Angeles Dodgers", {"BRO", "LAD"}), "MIA": ("Miami Marlins", {"FLA", "MIA"}),
    "MIL": ("Milwaukee Brewers", {"SEP", "MIL"}), "MIN": ("Minnesota Twins", {"WSH", "MIN"}),
    "NYM": ("New York Mets", {"NYM"}), "NYY": ("New York Yankees", {"NYY"}),
    "PHI": ("Philadelphia Phillies", {"PHI"}), "PIT": ("Pittsburgh Pirates", {"PIT"}),
    "SDP": ("San Diego Padres", {"SDP"}), "SEA": ("Seattle Mariners", {"SEA"}),
    "SFG": ("San Francisco Giants", {"NYG", "SFG"}), "STL": ("St. Louis Cardinals", {"STL"}),
    "TBR": ("Tampa Bay Rays", {"TBD", "TBR"}), "TEX": ("Texas Rangers", {"WSA", "TEX"}),
    "TOR": ("Toronto Blue Jays", {"TOR"}), "WSN": ("Washington Nationals", {"MON", "WSN"}),
}

POSITION_COLUMNS = {"C": "G_c", "1B": "G_1b", "2B": "G_2b", "3B": "G_3b", "SS": "G_ss", "LF": "G_lf", "CF": "G_cf", "RF": "G_rf"}


def _display_name(name):
    return {"Henry Aaron": "Hank Aaron", "Javy L�pez": "Javy López"}.get(name, name)


def _round_war(value):
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


@lru_cache(maxsize=1)
def _appearances():
    columns = ["playerID", "yearID", *POSITION_COLUMNS.values()]
    data = pd.read_csv(APPEARANCES_URL, usecols=columns)
    games = data.groupby("playerID", as_index=False)[list(POSITION_COLUMNS.values())].sum()
    games["position"] = games[list(POSITION_COLUMNS.values())].idxmax(axis=1).map({value: key for key, value in POSITION_COLUMNS.items()})
    return games[["playerID", "position"]]


@lru_cache(maxsize=30)
def get_lineup(team_key):
    team_name, team_ids = TEAMS[team_key]
    batting = bwar_bat()
    batting = batting.loc[batting["team_ID"].isin(team_ids) & (batting["pitcher"] != "Y")].copy()
    batting = batting.groupby(["player_ID", "name_common", "year_ID"], as_index=False)["WAR"].sum()
    batting = batting.merge(_appearances(), left_on="player_ID", right_on="playerID", how="inner")

    lineup = []
    for position in POSITION_COLUMNS:
        eligible = batting.loc[batting["position"] == position].sort_values("WAR", ascending=False)
        if not eligible.empty:
            row = eligible.iloc[0]
            lineup.append({"position": position, "name": _display_name(row["name_common"]),
                           "season": int(row["year_ID"]), "war": _round_war(row["WAR"]), "team": team_name})

    pitching = bwar_pitch()
    pitching = pitching.loc[pitching["team_ID"].isin(team_ids)].groupby(
        ["player_ID", "name_common", "year_ID"], as_index=False
    )["WAR"].sum().sort_values("WAR", ascending=False)
    if not pitching.empty:
        row = pitching.iloc[0]
        lineup.append({"position": "P", "name": _display_name(row["name_common"]), "season": int(row["year_ID"]),
                       "war": _round_war(row["WAR"]), "team": team_name})
    return tuple(lineup)


def get_player_names(team_key):
    return tuple(sorted({player["name"] for player in get_lineup(team_key)}, key=str.casefold))
