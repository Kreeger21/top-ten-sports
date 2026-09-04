from functools import lru_cache

import pandas as pd

from nba_court_service import DATA_PATH


ACCOLADES_PATH = DATA_PATH.with_name("nba_player_accolades.csv")
DRAFT_PATH = DATA_PATH.with_name("nba_player_drafts.csv")


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
def _accolades():
    frame = pd.read_csv(ACCOLADES_PATH, keep_default_na=False)
    frame["season"] = pd.to_numeric(frame["season"], errors="coerce").astype("Int64")
    frame["all_star"] = frame["all_star"].astype(str).str.casefold().eq("true")
    return frame


@lru_cache(maxsize=1)
def _drafts():
    frame = pd.read_csv(DRAFT_PATH)
    return frame.set_index("player_id").to_dict("index")


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
    player_accolades = _accolades().loc[lambda frame: frame["player_id"] == player_id]
    accolade_by_season = {int(row.season): row for row in player_accolades.itertuples()}
    history = []
    for season, season_rows in rows.groupby("season", sort=True):
        item = {
            "season": _season_label(season),
            "teams": " / ".join(dict.fromkeys(season_rows["team"].astype(str))),
            "all_star": bool(getattr(accolade_by_season.get(int(season)), "all_star", False)),
        }
        for column, _ in STAT_COLUMNS:
            value = season_rows[column].sum(min_count=1)
            item[column] = None if pd.isna(value) else int(round(value))
        history.append(item)
    totals = []
    for column, label in STAT_COLUMNS:
        value = rows[column].sum(min_count=1)
        totals.append({"label": label, "value": None if pd.isna(value) else int(round(value))})
    accolade_counts = {}
    all_star_count = int(player_accolades["all_star"].sum())
    if all_star_count:
        accolade_counts["All-Star"] = all_star_count
    for packed in player_accolades["accolades"]:
        for accolade in filter(None, str(packed).split("|")):
            if accolade.startswith(("All-NBA ", "All-ABA ", "All-BAA ")):
                accolade = "All-League Team"
            elif accolade.startswith("All-Defense "):
                accolade = "All-Defensive Team"
            elif accolade.startswith("All-Rookie "):
                accolade = "All-Rookie Team"
            accolade_counts[accolade] = accolade_counts.get(accolade, 0) + 1
    accolades = tuple(
        {"label": label, "count": count}
        for label, count in sorted(accolade_counts.items(), key=lambda item: (-item[1], item[0]))
    )
    positions = rows["pos"].dropna().astype(str)
    position = positions.mode().iloc[0] if not positions.empty else "—"
    first, last = int(rows["season"].min()), int(rows["season"].max())
    draft_record = _drafts().get(player_id)
    if draft_record and not pd.isna(draft_record.get("round")) and not pd.isna(draft_record.get("pick")):
        draft = (
            f'Round {int(draft_record["round"])} · Pick {int(draft_record["pick"])} · '
            f'{int(draft_record["year"])}'
        )
    else:
        draft = "Undrafted"
    return {
        "id": player_id,
        "name": rows.iloc[0]["player"],
        "position": position,
        "years": f"{first - 1} to {last}",
        "draft": draft,
        "seasons": len(history),
        "history": tuple(history),
        "totals": tuple(totals),
        "accolades": accolades,
    }
