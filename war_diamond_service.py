from functools import lru_cache
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
from pybaseball import bwar_bat, bwar_pitch


APPEARANCES_URL = "https://raw.githubusercontent.com/vincentarelbundock/Rdatasets/master/csv/Lahman/Appearances.csv"
BATTING_URL = "https://raw.githubusercontent.com/vincentarelbundock/Rdatasets/master/csv/Lahman/Batting.csv"
PEOPLE_URL = "https://raw.githubusercontent.com/vincentarelbundock/Rdatasets/master/csv/Lahman/People.csv"

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

# Lahman's historical team identifiers differ from Baseball-Reference's for several franchises.
LAHMAN_TEAM_IDS = {
    "ARI": {"ARI"}, "ATH": {"PHA", "KCA", "OAK"}, "ATL": {"BSN", "ML1", "ATL"},
    "BAL": {"SLA", "BAL"}, "BOS": {"BOS"}, "CHW": {"CHA"}, "CHC": {"CHN"}, "CIN": {"CIN"},
    "CLE": {"CLE"}, "COL": {"COL"}, "DET": {"DET"}, "HOU": {"HOU"}, "KCR": {"KCR"},
    "LAA": {"LAA", "CAL", "ANA"}, "LAD": {"BRO", "LAN"}, "MIA": {"FLO", "MIA"},
    "MIL": {"SE1", "ML4", "MIL"}, "MIN": {"WS1", "MIN"}, "NYM": {"NYN"}, "NYY": {"NYA"},
    "PHI": {"PHI"}, "PIT": {"PIT"}, "SDP": {"SDN"}, "SEA": {"SEA"},
    "SFG": {"NY1", "SFN"}, "STL": {"SLN"}, "TBR": {"TBA"}, "TEX": {"WS2", "TEX"},
    "TOR": {"TOR"}, "WSN": {"MON", "WAS"},
}

POSITION_COLUMNS = {"C": "G_c", "1B": "G_1b", "2B": "G_2b", "3B": "G_3b", "SS": "G_ss", "LF": "G_lf", "CF": "G_cf", "RF": "G_rf", "DH": "G_dh", "P": "G_p"}
ERA_OPTIONS = {
    "easy": "Easy — 1970–present",
    "medium": "Medium — 1950–present",
    "hard": "Hard — Modern Era (1901–present)",
}
WAR_MODE_OPTIONS = {
    "single_season": "Single-Season Leaders",
    "career": "Career with Franchise",
}
STAT_OPTIONS = {
    "war": {"label": "Baseball-Reference WAR", "short": "WAR", "column": "WAR", "digits": 1},
    "home_runs": {"label": "Home Runs", "short": "HR", "column": "HR", "digits": 0},
    "hits": {"label": "Hits", "short": "H", "column": "H", "digits": 0},
    "rbi": {"label": "Runs Batted In", "short": "RBI", "column": "RBI", "digits": 0},
    "runs": {"label": "Runs", "short": "R", "column": "R", "digits": 0},
    "stolen_bases": {"label": "Stolen Bases", "short": "SB", "column": "SB", "digits": 0},
    "walks": {"label": "Walks", "short": "BB", "column": "BB", "digits": 0},
    "doubles": {"label": "Doubles", "short": "2B", "column": "X2B", "digits": 0},
    "triples": {"label": "Triples", "short": "3B", "column": "X3B", "digits": 0},
}


def _display_name(name):
    return {"Henry Aaron": "Hank Aaron", "Javy L�pez": "Javy López"}.get(name, name)


def _round_war(value):
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _year_range(row):
    first, last = int(row["first_year"]), int(row["last_year"])
    return str(first) if first == last else f"{first}–{last}"


def _format_value(value, definition):
    digits = definition["digits"]
    return f'{float(value):.{digits}f} {definition["short"]}'


@lru_cache(maxsize=1)
def _appearances():
    columns = ["playerID", "yearID", *POSITION_COLUMNS.values()]
    data = pd.read_csv(APPEARANCES_URL, usecols=columns)
    games = data.groupby("playerID", as_index=False)[list(POSITION_COLUMNS.values())].sum()
    games["position"] = games[list(POSITION_COLUMNS.values())].idxmax(axis=1).map({value: key for key, value in POSITION_COLUMNS.items()})
    return games[["playerID", "position"]]


@lru_cache(maxsize=1)
def _batting_records():
    stat_columns = [definition["column"] for key, definition in STAT_OPTIONS.items() if key != "war"]
    batting = pd.read_csv(BATTING_URL, usecols=["playerID", "yearID", "teamID", *stat_columns])
    batting = batting.rename(columns={"yearID": "year_ID", "teamID": "team_ID"})
    people = pd.read_csv(PEOPLE_URL, usecols=["playerID", "nameFirst", "nameLast"])
    people["name_common"] = people[["nameFirst", "nameLast"]].fillna("").agg(" ".join, axis=1).str.strip()
    return batting.merge(people[["playerID", "name_common"]], on="playerID", how="left").rename(columns={"playerID": "player_ID"})


def _in_era(data, era):
    minimum_year = {"easy": 1970, "medium": 1950, "hard": 1901}.get(era)
    return data.loc[data["year_ID"] >= minimum_year] if minimum_year else data


def _position_lineup(data, team_name, war_mode, definition, positions=None):
    column = definition["column"]
    group_columns = ["player_ID", "name_common"] + ([] if war_mode == "career" else ["year_ID"])
    if war_mode == "career":
        data = data.groupby(group_columns, as_index=False).agg(
            value=(column, "sum"), first_year=("year_ID", "min"), last_year=("year_ID", "max")
        )
    else:
        data = data.groupby(group_columns, as_index=False)[column].sum().rename(columns={column: "value"})
    data = data.merge(_appearances(), left_on="player_ID", right_on="playerID", how="inner")
    lineup = []
    for position in positions or POSITION_COLUMNS:
        eligible = data.loc[data["position"] == position].sort_values("value", ascending=False)
        if not eligible.empty:
            row = eligible.iloc[0]
            lineup.append({"position": position, "name": _display_name(row["name_common"]),
                           "season": int(row["year_ID"]) if war_mode == "single_season" else None,
                           "years": _year_range(row) if war_mode == "career" else None,
                           "value": float(row["value"]), "display": _format_value(row["value"], definition),
                           "team": team_name})
    return lineup


def _pitching_lineup(data, team_name, war_mode, definition):
    group_columns = ["player_ID", "name_common"] + ([] if war_mode == "career" else ["year_ID"])
    aggregations = {"WAR": ("WAR", "sum"), "G": ("G", "sum"), "GS": ("GS", "sum")}
    if war_mode == "career":
        aggregations.update(first_year=("year_ID", "min"), last_year=("year_ID", "max"))
    data = data.groupby(group_columns, as_index=False).agg(**aggregations)
    data["pitching_role"] = data.apply(
        lambda row: "SP" if row["GS"] > 0 and row["GS"] >= row["G"] - row["GS"] else "RP", axis=1
    )
    lineup = []
    for role in ("SP", "RP"):
        eligible = data.loc[data["pitching_role"] == role].sort_values("WAR", ascending=False)
        if eligible.empty:
            continue
        row = eligible.iloc[0]
        value = _round_war(row["WAR"])
        lineup.append({"position": role, "name": _display_name(row["name_common"]),
                       "season": int(row["year_ID"]) if war_mode == "single_season" else None,
                       "years": _year_range(row) if war_mode == "career" else None,
                       "value": value, "display": _format_value(value, definition), "team": team_name})
    return lineup


@lru_cache(maxsize=900)
def get_lineup(team_key, era="medium", war_mode="single_season", stat_key="war"):
    team_name, team_ids = TEAMS[team_key]
    definition = STAT_OPTIONS[stat_key]
    if stat_key != "war":
        batting = _in_era(_batting_records().loc[
            lambda data: data["team_ID"].isin(LAHMAN_TEAM_IDS[team_key])
        ].copy(), era)
        batting_positions = [position for position in POSITION_COLUMNS if position != "P"]
        return tuple(_position_lineup(batting, team_name, war_mode, definition, batting_positions))

    batting = bwar_bat()
    batting = _in_era(batting.loc[batting["team_ID"].isin(team_ids) & (batting["pitcher"] != "Y")].copy(), era)
    lineup = _position_lineup(batting, team_name, war_mode, definition,
                              [position for position in POSITION_COLUMNS if position != "P"])
    for player in lineup:
        player["value"] = _round_war(player["value"])
        player["display"] = _format_value(player["value"], definition)

    pitching = _in_era(bwar_pitch().loc[lambda data: data["team_ID"].isin(team_ids)].copy(), era)
    lineup.extend(_pitching_lineup(pitching, team_name, war_mode, definition))
    return tuple(lineup)


@lru_cache(maxsize=900)
def get_player_names(team_key, era="medium", stat_key="war"):
    _, team_ids = TEAMS[team_key]
    if stat_key != "war":
        batting = _in_era(_batting_records().loc[
            lambda data: data["team_ID"].isin(LAHMAN_TEAM_IDS[team_key])
        ], era)
        return tuple(sorted({_display_name(name) for name in batting["name_common"].dropna()}, key=str.casefold))
    batting = _in_era(bwar_bat().loc[lambda data: data["team_ID"].isin(team_ids)], era)
    pitching = _in_era(bwar_pitch().loc[lambda data: data["team_ID"].isin(team_ids)], era)
    names = {_display_name(name) for name in pd.concat([batting["name_common"], pitching["name_common"]]).dropna()}
    return tuple(sorted(names, key=str.casefold))
