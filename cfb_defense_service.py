from functools import lru_cache
from pathlib import Path

import pandas as pd

from cfb_field_service import TEAMS, TIMEFRAME_OPTIONS


DATA_PATH = Path(__file__).with_name("data") / "cfb_defense_history.csv"
STAT_OPTIONS = {
    "tfl": {"label": "Tackles for Loss", "short": "TFL", "start": 2016},
    "tackles": {"label": "Tackles", "short": "TCK", "start": 2016},
    "interceptions": {"label": "Interceptions", "short": "INT", "start": 2004},
    "sacks": {"label": "Sacks", "short": "SCK", "start": 2016},
    "passes_defended": {"label": "Passes Defended", "short": "PD", "start": 2016},
}
GROUP_OPTIONS = {
    "DL": {"label": "Defensive Line", "count": 4},
    "LB": {"label": "Linebackers", "count": 3},
    "CB": {"label": "Cornerbacks", "count": 2},
    "S": {"label": "Safeties", "count": 2},
}
DEFAULT_STATS = {"DL": "sacks", "LB": "tackles", "CB": "interceptions", "S": "interceptions"}


@lru_cache(maxsize=1)
def _data():
    data = pd.read_csv(DATA_PATH)
    for stat in STAT_OPTIONS:
        data[stat] = pd.to_numeric(data[stat], errors="coerce").fillna(0)
    return data


def _year_range(row):
    first, last = int(row["first_year"]), int(row["last_year"])
    return str(first) if first == last else f"{first}–{last}"


def _format_value(value, stat):
    number = float(value)
    formatted = f"{number:.1f}" if not number.is_integer() else f"{int(number):,}"
    return f'{formatted} {STAT_OPTIONS[stat]["short"]}'


@lru_cache(maxsize=1024)
def get_lineup(team_key, timeframe="single_season", dl_stat="sacks", lb_stat="tackles",
               cb_stat="interceptions", s_stat="interceptions"):
    selected = {"DL": dl_stat, "LB": lb_stat, "CB": cb_stat, "S": s_stat}
    rows = _data().loc[lambda frame: frame["team"] == team_key].copy()
    lineup = []
    for group_key, group in GROUP_OPTIONS.items():
        stat = selected[group_key]
        eligible_groups = {group_key, "DB"} if group_key in {"CB", "S"} else {group_key}
        eligible = rows.loc[
            rows["field_group"].isin(eligible_groups) & (rows["season"] >= STAT_OPTIONS[stat]["start"])
        ]
        if timeframe == "career":
            ranked = eligible.groupby("player", as_index=False).agg(
                value=(stat, "sum"), first_year=("season", "min"), last_year=("season", "max")
            )
        else:
            ranked = eligible.groupby(["player", "season"], as_index=False)[stat].sum().rename(
                columns={stat: "value"}
            )
            ranked = ranked.sort_values(["value", "player"], ascending=[False, True]).drop_duplicates("player")
        ranked = ranked.loc[ranked["value"] > 0].sort_values(["value", "player"], ascending=[False, True])
        for index, (_, row) in enumerate(ranked.head(group["count"]).iterrows(), start=1):
            lineup.append({
                "position": f"{group_key}{index}", "group": group_key, "name": row["player"],
                "season": int(row["season"]) if timeframe == "single_season" else None,
                "years": _year_range(row) if timeframe == "career" else None,
                "display": _format_value(row["value"], stat),
                "stat_label": STAT_OPTIONS[stat]["label"], "team": team_key,
            })
    return tuple(lineup)


@lru_cache(maxsize=256)
def get_player_names(team_key):
    names = _data().loc[lambda frame: frame["team"] == team_key, "player"].dropna()
    return tuple(sorted(set(names), key=str.casefold))
