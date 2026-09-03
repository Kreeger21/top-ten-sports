from functools import lru_cache
from pathlib import Path

import pandas as pd


TEAMS = {
    "ATL": ("Atlanta Hawks", {"TRI", "MLH", "STL", "ATL"}),
    "BOS": ("Boston Celtics", {"BOS"}),
    "BKN": ("Brooklyn Nets", {"NYN", "NJN", "BRK"}),
    "CHA": ("Charlotte Hornets", {"CHH", "CHA", "CHO"}),
    "CHI": ("Chicago Bulls", {"CHI"}),
    "CLE": ("Cleveland Cavaliers", {"CLE"}),
    "DAL": ("Dallas Mavericks", {"DAL"}),
    "DEN": ("Denver Nuggets", {"DEN"}),
    "DET": ("Detroit Pistons", {"FTW", "DET"}),
    "GSW": ("Golden State Warriors", {"PHW", "SFW", "GSW"}),
    "HOU": ("Houston Rockets", {"SDR", "HOU"}),
    "IND": ("Indiana Pacers", {"IND"}),
    "LAC": ("LA Clippers", {"BUF", "SDC", "LAC"}),
    "LAL": ("Los Angeles Lakers", {"MNL", "LAL"}),
    "MEM": ("Memphis Grizzlies", {"VAN", "MEM"}),
    "MIA": ("Miami Heat", {"MIA"}),
    "MIL": ("Milwaukee Bucks", {"MIL"}),
    "MIN": ("Minnesota Timberwolves", {"MIN"}),
    "NOP": ("New Orleans Pelicans", {"NOH", "NOK", "NOP"}),
    "NYK": ("New York Knicks", {"NYK"}),
    "OKC": ("Oklahoma City Thunder", {"SEA", "OKC"}),
    "ORL": ("Orlando Magic", {"ORL"}),
    "PHI": ("Philadelphia 76ers", {"SYR", "PHI"}),
    "PHX": ("Phoenix Suns", {"PHO"}),
    "POR": ("Portland Trail Blazers", {"POR"}),
    "SAC": ("Sacramento Kings", {"ROC", "CIN", "KCO", "KCK", "SAC"}),
    "SAS": ("San Antonio Spurs", {"SAS"}),
    "TOR": ("Toronto Raptors", {"TOR"}),
    "UTA": ("Utah Jazz", {"NOJ", "UTA"}),
    "WAS": ("Washington Wizards", {"CHZ", "CHP", "BAL", "CAP", "WSB", "WAS"}),
}

POSITIONS = {
    "PG": "Point Guard", "SG": "Shooting Guard", "SF": "Small Forward",
    "PF": "Power Forward", "C": "Center",
}
STAT_OPTIONS = {
    "pts": {"label": "Points", "short": "PTS", "first": 1950},
    "trb": {"label": "Rebounds", "short": "REB", "first": 1951},
    "ast": {"label": "Assists", "short": "AST", "first": 1950},
    "stl": {"label": "Steals", "short": "STL", "first": 1974},
    "blk": {"label": "Blocks", "short": "BLK", "first": 1974},
    "x3p": {"label": "Three-Pointers Made", "short": "3PM", "first": 1980},
}
DEFAULT_STATS = {"PG": "ast", "SG": "pts", "SF": "pts", "PF": "trb", "C": "blk"}
TIMEFRAME_OPTIONS = {"single_season": "Single-Season Leaders", "career": "Career with Franchise"}
DATA_PATH = Path(__file__).with_name("data") / "nba_court_history.csv"


def _year_range(row):
    first, last = int(row["first_year"]) - 1, int(row["last_year"]) - 1
    return str(first) if first == last else f"{first}–{last}"


@lru_cache(maxsize=1)
def _data():
    data = pd.read_csv(DATA_PATH)
    for stat in STAT_OPTIONS:
        data[stat] = pd.to_numeric(data[stat], errors="coerce")
    return data


def _eligible_positions(value):
    primary = str(value).upper().split("-")[0]
    return {primary} if primary in POSITIONS else set()


@lru_cache(maxsize=512)
def get_lineup(team_key, timeframe="single_season", pg_stat="ast", sg_stat="pts",
               sf_stat="pts", pf_stat="trb", c_stat="blk"):
    selected = dict(zip(POSITIONS, (pg_stat, sg_stat, sf_stat, pf_stat, c_stat)))
    rows = _data().loc[lambda frame: frame["team"].isin(TEAMS[team_key][1])].copy()
    rows["eligible_positions"] = rows["pos"].map(_eligible_positions)
    lineup = []
    for position in POSITIONS:
        stat = selected[position]
        definition = STAT_OPTIONS[stat]
        eligible = rows.loc[
            rows["eligible_positions"].map(lambda choices: position in choices)
            & rows[stat].notna() & (rows["season"] >= definition["first"])
        ].copy()
        if timeframe == "career":
            # Position determines eligibility, but a career total includes every
            # season the eligible player recorded for the franchise.
            position_history = rows.assign(primary=rows["pos"].astype(str).str.upper().str.split("-").str[0])
            position_history = position_history.loc[position_history["primary"].isin(POSITIONS)]
            canonical = position_history.groupby(["player_id", "primary"]).size().reset_index(name="seasons")
            canonical = canonical.sort_values(
                ["player_id", "seasons", "primary"], ascending=[True, False, True]
            ).drop_duplicates("player_id")
            eligible_ids = set(canonical.loc[canonical["primary"] == position, "player_id"])
            eligible = rows.loc[
                rows["player_id"].isin(eligible_ids)
                & rows[stat].notna() & (rows["season"] >= definition["first"])
            ].copy()
            ranked = eligible.groupby(["player_id", "player"], as_index=False).agg(value=(stat, "sum"))
            tenure = rows.loc[rows["player_id"].isin(eligible_ids)].groupby(
                ["player_id", "player"], as_index=False
            ).agg(first_year=("season", "min"), last_year=("season", "max"))
            ranked = ranked.merge(tenure, on=["player_id", "player"], how="left")
        else:
            ranked = eligible.groupby(["player_id", "player", "season"], as_index=False)[stat].sum()
            ranked = ranked.rename(columns={stat: "value"})
        ranked = ranked.loc[ranked["value"] > 0].sort_values(
            ["value", "player"], ascending=[False, True]
        )
        if ranked.empty:
            continue
        row = ranked.iloc[0]
        value = int(round(float(row["value"])))
        lineup.append({
            "position": position, "name": row["player"],
            "season": int(row["season"] - 1) if timeframe == "single_season" else None,
            "years": _year_range(row) if timeframe == "career" else None,
            "value": value, "display": f'{value:,} {definition["short"]}',
            "stat_label": definition["label"], "team": TEAMS[team_key][0],
        })
    return tuple(lineup)


@lru_cache(maxsize=64)
def get_player_names(team_key):
    rows = _data().loc[lambda frame: frame["team"].isin(TEAMS[team_key][1])]
    return tuple(sorted(set(rows["player"].dropna()), key=str.casefold))
