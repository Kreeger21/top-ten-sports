from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import pandas as pd

from nfl_field_service import TEAMS, TIMEFRAME_OPTIONS
from nfl_service import MIN_SEASON, MAX_SEASON


DATA_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_{year}.csv"
STAT_OPTIONS = {
    "tfl": {"label": "Tackles for Loss", "short": "TFL"},
    "tackles": {"label": "Tackles", "short": "TCK"},
    "interceptions": {"label": "Interceptions", "short": "INT"},
    "sacks": {"label": "Sacks", "short": "SCK"},
    "forced_fumbles": {"label": "Forced Fumbles", "short": "FF"},
}
STAT_COLUMNS = {
    "tfl": "def_tackles_for_loss", "interceptions": "def_interceptions",
    "sacks": "def_sacks", "forced_fumbles": "def_fumbles_forced",
}
GROUP_OPTIONS = {
    "DL": {"label": "Defensive Line", "positions": {"DE", "DT", "NT", "DL"}, "count": 4},
    "LB": {"label": "Linebackers", "positions": {"LB", "ILB", "MLB", "OLB"}, "count": 3},
    "CB": {"label": "Cornerbacks", "positions": {"CB"}, "count": 3},
    "S": {"label": "Safeties", "positions": {"S", "FS", "SS"}, "count": 2},
}
USE_COLUMNS = ["player_id", "player_display_name", "position", "recent_team", "season",
               "def_tackles_solo", "def_tackles_with_assist", *STAT_COLUMNS.values()]


def _read_season(year):
    return pd.read_csv(DATA_URL.format(year=year), usecols=USE_COLUMNS)


@lru_cache(maxsize=1)
def _defensive_data():
    with ThreadPoolExecutor(max_workers=8) as executor:
        seasons = list(executor.map(_read_season, range(MIN_SEASON, MAX_SEASON + 1)))
    data = pd.concat(seasons, ignore_index=True)
    for column in USE_COLUMNS[5:]:
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0)
    data["tackles"] = data["def_tackles_solo"] + data["def_tackles_with_assist"]
    return data


def _year_range(row):
    first, last = int(row["first_year"]), int(row["last_year"])
    return str(first) if first == last else f"{first}–{last}"


def _format_value(value, stat_key):
    number = float(value)
    formatted = f"{number:.1f}" if not number.is_integer() else f"{int(number):,}"
    return f'{formatted} {STAT_OPTIONS[stat_key]["short"]}'


@lru_cache(maxsize=512)
def get_lineup(team_key, timeframe="single_season", dl_stat="sacks", lb_stat="tackles",
               cb_stat="interceptions", s_stat="interceptions"):
    selected_stats = {"DL": dl_stat, "LB": lb_stat, "CB": cb_stat, "S": s_stat}
    rows = _defensive_data().loc[lambda data: data["recent_team"].isin(TEAMS[team_key][1])].copy()
    lineup = []
    for group_key, group in GROUP_OPTIONS.items():
        stat_key = selected_stats[group_key]
        column = "tackles" if stat_key == "tackles" else STAT_COLUMNS[stat_key]
        eligible = rows.loc[rows["position"].astype(str).str.upper().isin(group["positions"])]
        group_columns = ["player_id", "player_display_name"] + ([] if timeframe == "career" else ["season"])
        if timeframe == "career":
            ranked = eligible.groupby(group_columns, as_index=False).agg(
                value=(column, "sum"), first_year=("season", "min"), last_year=("season", "max")
            )
        else:
            ranked = eligible.groupby(group_columns, as_index=False)[column].sum().rename(columns={column: "value"})
            ranked = ranked.sort_values(["value", "player_display_name"], ascending=[False, True]).drop_duplicates("player_id")
        ranked = ranked.loc[ranked["value"] > 0].sort_values(["value", "player_display_name"], ascending=[False, True])
        for index, (_, row) in enumerate(ranked.head(group["count"]).iterrows(), start=1):
            lineup.append({"position": f"{group_key}{index}", "group": group_key,
                           "name": row["player_display_name"],
                           "season": int(row["season"]) if timeframe == "single_season" else None,
                           "years": _year_range(row) if timeframe == "career" else None,
                           "display": _format_value(row["value"], stat_key), "stat_label": STAT_OPTIONS[stat_key]["label"],
                           "team": TEAMS[team_key][0]})
    return tuple(lineup)


@lru_cache(maxsize=64)
def get_player_names(team_key):
    rows = _defensive_data().loc[lambda data: data["recent_team"].isin(TEAMS[team_key][1])]
    defensive_positions = set().union(*(group["positions"] for group in GROUP_OPTIONS.values()))
    names = rows.loc[rows["position"].astype(str).str.upper().isin(defensive_positions), "player_display_name"].dropna()
    return tuple(sorted(set(names), key=str.casefold))
