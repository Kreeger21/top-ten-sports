from functools import lru_cache
from pathlib import Path

import pandas as pd

import nfl_service


TEAMS = {
    "ARI": ("Arizona Cardinals", {"ARI"}), "ATL": ("Atlanta Falcons", {"ATL"}),
    "BAL": ("Baltimore Ravens", {"BAL"}), "BUF": ("Buffalo Bills", {"BUF"}),
    "CAR": ("Carolina Panthers", {"CAR"}), "CHI": ("Chicago Bears", {"CHI"}),
    "CIN": ("Cincinnati Bengals", {"CIN"}), "CLE": ("Cleveland Browns", {"CLE"}),
    "DAL": ("Dallas Cowboys", {"DAL"}), "DEN": ("Denver Broncos", {"DEN"}),
    "DET": ("Detroit Lions", {"DET"}), "GB": ("Green Bay Packers", {"GB"}),
    "HOU": ("Houston Texans", {"HOU"}), "IND": ("Indianapolis Colts", {"IND"}),
    "JAX": ("Jacksonville Jaguars", {"JAX"}), "KC": ("Kansas City Chiefs", {"KC"}),
    "LV": ("Las Vegas Raiders", {"OAK", "LV"}), "LAC": ("Los Angeles Chargers", {"SD", "LAC"}),
    "LAR": ("Los Angeles Rams", {"STL", "LA", "LAR"}), "MIA": ("Miami Dolphins", {"MIA"}),
    "MIN": ("Minnesota Vikings", {"MIN"}), "NE": ("New England Patriots", {"NE"}),
    "NO": ("New Orleans Saints", {"NO"}), "NYG": ("New York Giants", {"NYG"}),
    "NYJ": ("New York Jets", {"NYJ"}), "PHI": ("Philadelphia Eagles", {"PHI"}),
    "PIT": ("Pittsburgh Steelers", {"PIT"}), "SEA": ("Seattle Seahawks", {"SEA"}),
    "SF": ("San Francisco 49ers", {"SF"}), "TB": ("Tampa Bay Buccaneers", {"TB"}),
    "TEN": ("Tennessee Titans", {"TEN"}), "WAS": ("Washington Commanders", {"WAS"}),
}

TIMEFRAME_OPTIONS = {"single_season": "Single-Season Leaders", "career": "Career with Franchise"}
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
HISTORY_PATH = Path(__file__).with_name("data") / "nfl_offense_history.csv"
LATEST_DATA_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_{year}.csv"
LATEST_COLUMNS = [
    "player_id", "player_display_name", "position", "recent_team", "season",
    "passing_yards", "passing_tds", "rushing_yards", "rushing_tds",
    "receiving_yards", "receiving_tds",
]


def _normalized_position(position):
    position = str(position).upper()
    return "RB" if position in {"HB", "FB"} else position


def _year_range(row):
    first, last = int(row["first_year"]), int(row["last_year"])
    return str(first) if first == last else f"{first}–{last}"


@lru_cache(maxsize=1)
def _historical_data():
    data = pd.read_csv(HISTORY_PATH)
    for options in POSITION_STAT_OPTIONS.values():
        for column in options:
            data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0)
    return data


@lru_cache(maxsize=1)
def _latest_data():
    return pd.read_csv(LATEST_DATA_URL.format(year=nfl_service.MAX_SEASON), usecols=LATEST_COLUMNS)


def _team_rows(team_key):
    current = nfl_service._weekly_data()
    current = current.loc[
        (current["season_type"] == "REG") & current["recent_team"].isin(TEAMS[team_key][1])
    ].copy()
    current["field_position"] = current["position"].map(_normalized_position)
    if int(current["season"].max()) < nfl_service.MAX_SEASON:
        latest = _latest_data()
        latest = latest.loc[latest["recent_team"].isin(TEAMS[team_key][1])].copy()
        latest["field_position"] = latest["position"].map(_normalized_position)
        current = pd.concat([current, latest], ignore_index=True, sort=False)
    history = _historical_data().loc[
        lambda data: data["recent_team"].isin(TEAMS[team_key][1] | {team_key})
    ].copy()
    return pd.concat([history, current], ignore_index=True, sort=False)


@lru_cache(maxsize=512)
def get_lineup(team_key, timeframe="single_season", qb_stat="passing_yards",
               rb_stat="rushing_yards", wr_stat="receiving_yards", te_stat="receiving_yards"):
    selected_stats = {"QB": qb_stat, "RB": rb_stat, "WR": wr_stat, "TE": te_stat}
    rows, team_name = _team_rows(team_key), TEAMS[team_key][0]
    lineup = []
    for base_position, group in GROUP_OPTIONS.items():
        stat_column = selected_stats[base_position]
        definition = POSITION_STAT_OPTIONS[base_position][stat_column]
        eligible = rows.loc[rows["field_position"] == base_position].copy()
        eligible[stat_column] = pd.to_numeric(eligible[stat_column], errors="coerce").fillna(0)
        group_columns = ["player_display_name"] + ([] if timeframe == "career" else ["season"])
        if timeframe == "career":
            ranked = eligible.groupby(group_columns, as_index=False).agg(
                value=(stat_column, "sum"), first_year=("season", "min"), last_year=("season", "max")
            )
        else:
            ranked = eligible.groupby(group_columns, as_index=False)[stat_column].sum().rename(
                columns={stat_column: "value"}
            )
        ranked = ranked.loc[ranked["value"] > 0].sort_values(
            ["value", "player_display_name"], ascending=[False, True]
        )
        if timeframe == "single_season" and group["count"] > 1:
            ranked = ranked.drop_duplicates("player_display_name", keep="first")
        for index, (_, row) in enumerate(ranked.head(group["count"]).iterrows(), start=1):
            position = f"{base_position}{index}" if group["count"] > 1 else base_position
            value = int(round(float(row["value"])))
            lineup.append({"position": position, "group": base_position, "name": row["player_display_name"],
                           "season": int(row["season"]) if timeframe == "single_season" else None,
                           "years": _year_range(row) if timeframe == "career" else None,
                           "value": value, "display": f'{value:,} {definition["short"]}',
                           "stat_label": definition["label"], "team": team_name})
    return tuple(lineup)


@lru_cache(maxsize=64)
def get_player_names(team_key):
    rows = _team_rows(team_key)
    names = rows.loc[rows["field_position"].isin(GROUP_OPTIONS), "player_display_name"].dropna()
    return tuple(sorted(set(names), key=str.casefold))
