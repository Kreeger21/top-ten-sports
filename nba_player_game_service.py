from functools import lru_cache

import pandas as pd

from nba_court_service import DATA_PATH


STAT_COLUMNS = (
    ("pts", "PTS"), ("trb", "REB"), ("ast", "AST"),
    ("stl", "STL"), ("blk", "BLK"), ("x3p", "3PM"),
)


def _season_label(end_year):
    start_year = int(end_year) - 1
    return f"{start_year}–{str(end_year)[-2:]}"


@lru_cache(maxsize=1)
def _data():
    frame = pd.read_csv(DATA_PATH)
    for column, _ in STAT_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


@lru_cache(maxsize=1)
def player_choices():
    summary = _data().groupby(["player_id", "player"], as_index=False).agg(
        seasons=("season", "nunique"), points=("pts", "sum"),
    )
    # Established careers produce a useful trail without making the answer
    # depend on a one-season player the audience is unlikely to recognize.
    summary = summary.loc[(summary["seasons"] >= 5) & (summary["points"] >= 5000)]
    summary = summary.sort_values("player", key=lambda values: values.str.casefold())
    return tuple({"id": row.player_id, "name": row.player} for row in summary.itertuples())


@lru_cache(maxsize=1024)
def career(player_id):
    rows = _data().loc[lambda frame: frame["player_id"] == player_id].copy()
    if rows.empty:
        raise KeyError(player_id)
    rows = rows.sort_values(["season", "team"])
    history = []
    for season, season_rows in rows.groupby("season", sort=True):
        item = {
            "season": _season_label(season),
            "teams": " / ".join(dict.fromkeys(season_rows["team"].astype(str))),
        }
        for column, _ in STAT_COLUMNS:
            value = season_rows[column].sum(min_count=1)
            item[column] = None if pd.isna(value) else int(round(value))
        history.append(item)
    totals = []
    for column, label in STAT_COLUMNS:
        value = rows[column].sum(min_count=1)
        totals.append({"label": label, "value": None if pd.isna(value) else int(round(value))})
    positions = rows["pos"].dropna().astype(str)
    position = positions.mode().iloc[0] if not positions.empty else "—"
    first, last = int(rows["season"].min()), int(rows["season"].max())
    return {
        "id": player_id,
        "name": rows.iloc[0]["player"],
        "position": position,
        "years": f"{_season_label(first)} to {_season_label(last)}",
        "seasons": len(history),
        "history": tuple(history),
        "totals": tuple(totals),
    }
