from functools import lru_cache

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

METRIC_OPTIONS = {
    "yardage": {"label": "Yardage", "short": "YDS"},
    "touchdowns": {"label": "Touchdowns", "short": "TD"},
}

TIMEFRAME_OPTIONS = {
    "single_season": "Single-Season Leaders",
    "career": "Career with Franchise",
}

POSITION_STATS = {
    "yardage": {"QB": "passing_yards", "RB": "rushing_yards", "FB": "rushing_yards",
                 "WR": "receiving_yards", "TE": "receiving_yards"},
    "touchdowns": {"QB": "passing_tds", "RB": "rushing_tds", "FB": "rushing_tds",
                    "WR": "receiving_tds", "TE": "receiving_tds"},
}


def _normalized_position(position):
    position = str(position).upper()
    return "RB" if position == "HB" else position


def _year_range(row):
    first, last = int(row["first_year"]), int(row["last_year"])
    return str(first) if first == last else f"{first}–{last}"


def _team_rows(team_key):
    data = nfl_service._weekly_data()
    rows = data.loc[(data["season_type"] == "REG") & data["recent_team"].isin(TEAMS[team_key][1])].copy()
    rows["field_position"] = rows["position"].map(_normalized_position)
    return rows


@lru_cache(maxsize=256)
def get_lineup(team_key, timeframe="single_season", metric="yardage"):
    rows, team_name = _team_rows(team_key), TEAMS[team_key][0]
    lineup = []
    for base_position, stat_column in POSITION_STATS[metric].items():
        eligible = rows.loc[rows["field_position"] == base_position].copy()
        eligible[stat_column] = pd.to_numeric(eligible[stat_column], errors="coerce").fillna(0)
        group_columns = ["player_id", "player_display_name"] + ([] if timeframe == "career" else ["season"])
        if timeframe == "career":
            ranked = eligible.groupby(group_columns, as_index=False).agg(
                value=(stat_column, "sum"), first_year=("season", "min"), last_year=("season", "max")
            )
        else:
            ranked = eligible.groupby(group_columns, as_index=False)[stat_column].sum().rename(columns={stat_column: "value"})
        ranked = ranked.loc[ranked["value"] > 0].sort_values(["value", "player_display_name"], ascending=[False, True])
        if timeframe == "single_season" and base_position == "WR":
            ranked = ranked.drop_duplicates("player_id", keep="first")
        count = 2 if base_position == "WR" else 1
        for index, (_, row) in enumerate(ranked.head(count).iterrows(), start=1):
            position = f"WR{index}" if base_position == "WR" else base_position
            value = int(round(float(row["value"])))
            lineup.append({"position": position, "name": row["player_display_name"],
                           "season": int(row["season"]) if timeframe == "single_season" else None,
                           "years": _year_range(row) if timeframe == "career" else None,
                           "value": value, "display": f'{value:,} {METRIC_OPTIONS[metric]["short"]}',
                           "team": team_name})
    return tuple(lineup)


@lru_cache(maxsize=64)
def get_player_names(team_key):
    rows = _team_rows(team_key)
    names = rows.loc[rows["field_position"].isin(POSITION_STATS["yardage"]), "player_display_name"].dropna()
    return tuple(sorted(set(names), key=str.casefold))
