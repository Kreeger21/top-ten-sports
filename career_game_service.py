from functools import lru_cache
from pathlib import Path

import pandas as pd


DATA_DIR = Path(__file__).with_name("data")
CONFIG = {
    "mlb": {
        "file": "mlb_career_history.csv", "name": "player", "team": "team", "position": None,
        "stats": (("games", "G"), ("hits", "H"), ("home_runs", "HR"), ("rbi", "RBI"),
                  ("stolen_bases", "SB"), ("wins", "W"), ("strikeouts", "SO"), ("saves", "SV")),
        "eligible": lambda row: row.seasons >= 5 and (row.hits >= 700 or row.strikeouts >= 700),
    },
    "nfl": {
        "file": "nfl_career_history.csv",
        "name": "player_display_name", "team": "recent_team", "position": "position",
        "stats": (("passing_yards", "PASS YDS"), ("passing_tds", "PASS TD"),
                  ("rushing_yards", "RUSH YDS"), ("rushing_tds", "RUSH TD"),
                  ("receiving_yards", "REC YDS"), ("receiving_tds", "REC TD"),
                  ("tackles", "TACKLES"), ("def_sacks", "SACKS"),
                  ("def_interceptions", "INT")),
        "eligible": lambda row: row.seasons >= 4 and max(row.passing_yards / 2, row.rushing_yards,
                                                           row.receiving_yards, row.tackles * 10,
                                                           row.def_sacks * 100, row.def_interceptions * 100) >= 1500,
    },
    "cfb": {
        "files": ("cfb_offense_history.csv", "cfb_defense_history.csv"),
        "name": "player", "team": "team", "position": "position",
        "stats": (("passing_yards", "PASS YDS"), ("passing_tds", "PASS TD"),
                  ("rushing_yards", "RUSH YDS"), ("rushing_tds", "RUSH TD"),
                  ("receiving_yards", "REC YDS"), ("receiving_tds", "REC TD"),
                  ("tackles", "TACKLES"), ("sacks", "SACKS"), ("tfl", "TFL"),
                  ("interceptions", "INT")),
        "eligible": lambda row: row.seasons >= 2 and max(row.passing_yards / 2, row.rushing_yards,
                                                           row.receiving_yards, row.tackles * 10,
                                                           row.sacks * 100, row.interceptions * 100) >= 1000,
    },
}


def _standardize(sport, frame, source):
    config = CONFIG[sport]
    renames = {config["name"]: "player", config["team"]: "team"}
    if sport == "nfl":
        position_column = "field_position" if "offense" in source else "position"
        renames[position_column] = "position"
    elif sport == "cfb":
        position_column = "field_position" if "offense" in source else "field_group"
        renames[position_column] = "position"
    frame = frame.rename(columns=renames)
    for column, _ in config["stats"]:
        if column not in frame:
            frame[column] = 0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    frame["player_id"] = frame["player_id"].astype(str)
    frame["season"] = pd.to_numeric(frame["season"], errors="coerce")
    if "position" not in frame:
        frame["position"] = "—"
    return frame[["season", "player_id", "player", "team", "position",
                  *[column for column, _ in config["stats"]]]]


@lru_cache(maxsize=3)
def _data(sport):
    config = CONFIG[sport]
    files = config["files"] if "files" in config else (config["file"],)
    frames = [_standardize(sport, pd.read_csv(DATA_DIR / filename), filename) for filename in files]
    data = pd.concat(frames, ignore_index=True)
    stats = [column for column, _ in config["stats"]]
    return data.groupby(["season", "player_id", "player", "team", "position"], as_index=False)[stats].sum()


@lru_cache(maxsize=3)
def player_choices(sport):
    config, data = CONFIG[sport], _data(sport)
    stats = [column for column, _ in config["stats"]]
    summary = data.groupby(["player_id", "player"], as_index=False).agg(
        seasons=("season", "nunique"), **{column: (column, "sum") for column in stats},
    )
    summary = summary.loc[summary.apply(config["eligible"], axis=1)]
    summary = summary.sort_values("player", key=lambda values: values.str.casefold())
    return tuple({"id": row.player_id, "name": row.player} for row in summary.itertuples())


@lru_cache(maxsize=2048)
def career(sport, player_id):
    config = CONFIG[sport]
    rows = _data(sport).loc[lambda frame: frame["player_id"] == str(player_id)].copy()
    if rows.empty:
        raise KeyError(player_id)
    stats = config["stats"]
    totals_by_column = {column: int(round(rows[column].sum())) for column, _ in stats}
    positions = rows.loc[rows["position"] != "—", "position"].astype(str)
    position = positions.mode().iloc[0] if not positions.empty else "—"
    if sport == "mlb":
        is_pitcher = totals_by_column["strikeouts"] >= totals_by_column["hits"]
        position = "Pitcher" if is_pitcher else "Hitter"
        wanted = {"games", "wins", "strikeouts", "saves"} if is_pitcher else {"games", "hits", "home_runs", "rbi", "stolen_bases"}
    elif position in {"QB"}:
        wanted = {"passing_yards", "passing_tds", "rushing_yards", "rushing_tds"}
    elif position in {"RB", "HB", "FB", "WR", "TE"}:
        wanted = {"rushing_yards", "rushing_tds", "receiving_yards", "receiving_tds"}
    elif sport == "nfl":
        wanted = {"tackles", "def_sacks", "def_interceptions"}
    else:
        wanted = {"tackles", "sacks", "tfl", "interceptions"}
    active_stats = tuple((column, label) for column, label in stats
                         if column in wanted and totals_by_column[column] != 0)
    if not active_stats:
        active_stats = tuple((column, label) for column, label in stats if totals_by_column[column] != 0)[:6]
    history = []
    for season, season_rows in rows.groupby("season", sort=True):
        item = {"season": str(int(season)), "teams": " / ".join(dict.fromkeys(season_rows["team"].astype(str)))}
        for column, _ in active_stats:
            item[column] = int(round(season_rows[column].sum()))
        history.append(item)
    totals = tuple({"label": label, "value": totals_by_column[column]} for column, label in active_stats)
    return {"id": str(player_id), "name": rows.iloc[0]["player"], "position": position,
            "years": f'{int(rows["season"].min())} to {int(rows["season"].max())}',
            "seasons": len(history), "history": tuple(history), "totals": totals,
            "stat_columns": active_stats}


def stat_columns(sport):
    return CONFIG[sport]["stats"]
