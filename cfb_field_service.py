from functools import lru_cache
from pathlib import Path

import pandas as pd


DATA_PATH = Path(__file__).with_name("data") / "cfb_offense_history.csv"
TEAMS_PATH = Path(__file__).with_name("data") / "cfb_offense_teams.txt"
TEAMS = {name: (name, {name}) for name in TEAMS_PATH.read_text(encoding="utf-8").splitlines() if name}
TIMEFRAME_OPTIONS = {"single_season": "Single-Season Leaders", "career": "Career with Program"}
GROUP_OPTIONS = {
    "QB": {"label": "Quarterback", "count": 1},
    "RB": {"label": "Running Backs", "count": 2},
    "WR": {"label": "Wide Receivers", "count": 3},
    "TE": {"label": "Tight End", "count": 1},
}
POSITION_STAT_OPTIONS = {
    "QB": {
        "passing_yards": {"label": "Passing Yards", "short": "YDS"},
        "passing_tds": {"label": "Passing Touchdowns", "short": "TD"},
    },
    "RB": {
        "rushing_yards": {"label": "Rushing Yards", "short": "YDS"},
        "rushing_tds": {"label": "Rushing Touchdowns", "short": "TD"},
    },
    "WR": {
        "receiving_yards": {"label": "Receiving Yards", "short": "YDS"},
        "receiving_tds": {"label": "Receiving Touchdowns", "short": "TD"},
    },
    "TE": {
        "receiving_yards": {"label": "Receiving Yards", "short": "YDS"},
        "receiving_tds": {"label": "Receiving Touchdowns", "short": "TD"},
    },
}
DEFAULT_STATS = {
    "QB": "passing_yards", "RB": "rushing_yards",
    "WR": "receiving_yards", "TE": "receiving_yards",
}


def _year_range(row):
    first, last = int(row["first_year"]), int(row["last_year"])
    return str(first) if first == last else f"{first}–{last}"


@lru_cache(maxsize=1)
def _data():
    data = pd.read_csv(DATA_PATH)
    for options in POSITION_STAT_OPTIONS.values():
        for column in options:
            data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0)
    return data


@lru_cache(maxsize=1024)
def get_lineup(team_key, timeframe="single_season", qb_stat="passing_yards",
               rb_stat="rushing_yards", wr_stat="receiving_yards", te_stat="receiving_yards"):
    selected = {"QB": qb_stat, "RB": rb_stat, "WR": wr_stat, "TE": te_stat}
    rows = _data().loc[lambda frame: frame["team"] == team_key].copy()
    lineup = []
    for base_position, group in GROUP_OPTIONS.items():
        stat = selected[base_position]
        definition = POSITION_STAT_OPTIONS[base_position][stat]
        eligible = rows.loc[rows["field_position"] == base_position].copy()
        if timeframe == "career":
            ranked = eligible.groupby("player", as_index=False).agg(
                value=(stat, "sum"), first_year=("season", "min"), last_year=("season", "max")
            )
        else:
            ranked = eligible.groupby(["player", "season"], as_index=False)[stat].sum().rename(
                columns={stat: "value"}
            )
        ranked = ranked.loc[ranked["value"] > 0].sort_values(
            ["value", "player"], ascending=[False, True]
        )
        if timeframe == "single_season" and group["count"] > 1:
            ranked = ranked.drop_duplicates("player", keep="first")
        for index, (_, row) in enumerate(ranked.head(group["count"]).iterrows(), start=1):
            position = f"{base_position}{index}" if group["count"] > 1 else base_position
            value = int(round(float(row["value"])))
            lineup.append({
                "position": position, "group": base_position, "name": row["player"],
                "season": int(row["season"]) if timeframe == "single_season" else None,
                "years": _year_range(row) if timeframe == "career" else None,
                "value": value, "display": f'{value:,} {definition["short"]}',
                "stat_label": definition["label"], "team": team_key,
            })
    return tuple(lineup)


@lru_cache(maxsize=256)
def get_player_names(team_key):
    names = _data().loc[lambda frame: frame["team"] == team_key, "player"].dropna()
    return tuple(sorted(set(names), key=str.casefold))
