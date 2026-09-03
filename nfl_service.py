from functools import lru_cache

import pandas as pd


NFL_DATA_URL = "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv"
MIN_SEASON = 1999
MAX_SEASON = 2025

STAT_OPTIONS = {
    "passing": {
        "passing_yards": {"label": "Passing Yards", "short": "YDS"},
        "passing_tds": {"label": "Passing Touchdowns", "short": "TD"},
        "completions": {"label": "Completions", "short": "CMP"},
        "attempts": {"label": "Pass Attempts", "short": "ATT"},
        "interceptions": {"label": "Interceptions Thrown", "short": "INT"},
    },
    "rushing": {
        "rushing_yards": {"label": "Rushing Yards", "short": "YDS"},
        "rushing_tds": {"label": "Rushing Touchdowns", "short": "TD"},
        "carries": {"label": "Rushing Attempts", "short": "CAR"},
        "rushing_first_downs": {"label": "Rushing First Downs", "short": "1D"},
    },
    "receiving": {
        "receiving_yards": {"label": "Receiving Yards", "short": "YDS"},
        "receiving_tds": {"label": "Receiving Touchdowns", "short": "TD"},
        "receptions": {"label": "Receptions", "short": "REC"},
        "targets": {"label": "Targets", "short": "TGT"},
    },
    "fantasy": {
        "fantasy_points": {"label": "Fantasy Points", "short": "FPTS", "decimal": True},
        "fantasy_points_ppr": {"label": "PPR Fantasy Points", "short": "PPR", "decimal": True},
    },
}


@lru_cache(maxsize=1)
def _weekly_data():
    return pd.read_csv(NFL_DATA_URL, low_memory=False)


@lru_cache(maxsize=64)
def _season_data(season):
    data = _weekly_data()
    rows = data.loc[(data["season"] == season) & (data["season_type"] == "REG")].copy()
    if rows.empty:
        return rows

    stat_columns = [key for options in STAT_OPTIONS.values() for key in options]
    for column in stat_columns:
        rows[column] = pd.to_numeric(rows[column], errors="coerce").fillna(0)

    grouped = rows.groupby(["player_id", "player_display_name"], dropna=False).agg(
        **{column: (column, "sum") for column in stat_columns},
        team=("recent_team", lambda teams: "/".join(dict.fromkeys(teams.dropna().astype(str)))),
        position=("position", "last"),
    )
    return grouped.reset_index()


def get_leaders(season, group, stat_key, limit=10):
    definition = STAT_OPTIONS[group][stat_key]
    data = _season_data(season)
    if data.empty:
        return []

    eligible = data.loc[data[stat_key] > 0].sort_values(stat_key, ascending=False).head(limit)
    return [
        {
            "name": row["player_display_name"],
            "team": row["team"] or "—",
            "value": f'{row[stat_key]:.1f}' if definition.get("decimal") else f'{row[stat_key]:,.0f}',
            "sortable_value": float(row[stat_key]),
        }
        for _, row in eligible.iterrows()
    ]


@lru_cache(maxsize=64)
def get_player_names(season, group):
    data = _season_data(season)
    if data.empty:
        return ()
    group_stats = list(STAT_OPTIONS[group])
    eligible = data.loc[data[group_stats].sum(axis=1) > 0, "player_display_name"].dropna()
    return tuple(sorted(set(eligible), key=str.casefold))
