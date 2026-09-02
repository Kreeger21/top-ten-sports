from functools import lru_cache, reduce
import re
from urllib.request import Request, urlopen

import pandas as pd
from bs4 import BeautifulSoup


DATA_URL = "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/player_stats/csv/player_stats_{season}.csv"
D1SPORTSNET_RUSHING_URL = "https://d1sportsnet.com/football/stats/{season}/ir.php"
MIN_SEASON = 1996
MAX_SEASON = 2026

FBS_CONFERENCES = {
    "ACC", "American Athletic", "Big 12", "Big Ten", "Conference USA",
    "FBS Independents", "Mid-American", "Mountain West", "Pac-12", "SEC", "Sun Belt",
}

STAT_OPTIONS = {
    "passing": {
        "passing_yards": {"label": "Passing Yards", "short": "YDS"},
        "passing_tds": {"label": "Passing Touchdowns", "short": "TD"},
        "completions": {"label": "Completions", "short": "CMP"},
        "attempts": {"label": "Pass Attempts", "short": "ATT"},
        "interceptions_thrown": {"label": "Interceptions Thrown", "short": "INT"},
    },
    "rushing": {
        "rushing_yards": {"label": "Rushing Yards", "short": "YDS"},
        "rushing_tds": {"label": "Rushing Touchdowns", "short": "TD"},
        "carries": {"label": "Rushing Attempts", "short": "CAR"},
    },
    "receiving": {
        "receiving_yards": {"label": "Receiving Yards", "short": "YDS"},
        "receiving_tds": {"label": "Receiving Touchdowns", "short": "TD"},
        "receptions": {"label": "Receptions", "short": "REC"},
    },
    "defense": {
        "interceptions": {"label": "Interceptions", "short": "INT"},
        "sacks": {"label": "Sacks", "short": "SACK"},
        "forced_fumbles": {"label": "Forced Fumbles", "short": "FF"},
        "pass_breakups": {"label": "Pass Breakups", "short": "PBU"},
    },
    "kicking": {
        "field_goals_made": {"label": "Field Goals Made", "short": "FGM"},
        "field_goals_attempted": {"label": "Field Goals Attempted", "short": "FGA"},
    },
}


def stat_min_season(group, stat_key):
    """The official archive has complete rushing tables back to 1996."""
    if group == "rushing" and stat_key in {"rushing_yards", "carries"}:
        return MIN_SEASON
    if group == "rushing" and stat_key == "rushing_tds":
        return 2000
    return 2014


@lru_cache(maxsize=16)
def _raw_season(season):
    return pd.read_csv(DATA_URL.format(season=season), low_memory=False)


@lru_cache(maxsize=16)
def _official_rushing_data(season):
    """Load season rushing totals from an NCAA-statistics archive.

    Unlike totals reconstructed from individual plays, these values include
    postseason games and the official corrections applied after games.
    """
    request = Request(
        D1SPORTSNET_RUSHING_URL.format(season=season),
        headers={"User-Agent": "TopTenSports/1.0"},
    )
    with urlopen(request, timeout=15) as response:
        soup = BeautifulSoup(response.read(), "html.parser")

    records = []
    for row in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"], recursive=False)]
        if len(cells) != 9 or cells[0] in {"", "Rank"}:
            continue
        try:
            records.append({
                "player_id": f"{cells[1]}|{cells[2]}",
                "player": cells[1],
                "team": cells[2],
                "games": int(cells[5].replace(",", "")),
                "carries": int(cells[6].replace(",", "")),
                "rushing_yards": int(cells[7].replace(",", "")),
                "rushing_tds": int(cells[8].replace(",", "")),
            })
        except ValueError:
            continue
    if not records:
        # Older archive pages store the leaderboard as fixed-width text rather
        # than table rows. Formats vary slightly, but always end in numeric
        # columns following "Player, Team".
        blocks = [text for text in soup.stripped_strings if "Rushing" in text and "\n" in text]
        for line in (blocks[-1].splitlines() if blocks else []):
            match = re.match(
                r"^\s*\d+\.?\s+(.+?),\s+(.+?)\s+(?:-+\s+)?(\d+(?:\s+[\d.]+){3,5})\s*$",
                line,
            )
            if not match:
                continue
            player, team, number_text = match.groups()
            numbers = number_text.split()
            if len(numbers) == 4:  # 1996: CAR, YDS, AVG, YDSPG
                carries, yards = numbers[:2]
                games, touchdowns = 0, 0
            else:  # Later pages: G, CAR, YDS, TD, [AVG], YDSPG
                games, carries, yards, touchdowns = numbers[:4]
            records.append({
                "player_id": f"{player}|{team}",
                "player": player,
                "team": team.rstrip(" -"),
                "games": int(games),
                "carries": int(carries),
                "rushing_yards": int(yards),
                "rushing_tds": int(touchdowns),
            })
    if not records:
        raise ValueError(f"No official rushing statistics found for {season}")
    return pd.DataFrame.from_records(records)


def _event(data, player_id, player_name, stat_name, value=None, team="team", mask=None):
    rows = data if mask is None else data.loc[mask]
    rows = rows.loc[rows[player_name].notna(), [player_id, player_name, team] + ([value] if value else [])].copy()
    rows.columns = ["player_id", "player", "team"] + ([stat_name] if value else [])
    if value:
        rows[stat_name] = pd.to_numeric(rows[stat_name], errors="coerce").fillna(0)
        return rows.groupby(["player_id", "player", "team"], as_index=False)[stat_name].sum()
    return rows.groupby(["player_id", "player", "team"], as_index=False).size().rename(columns={"size": stat_name})


def _combine(frames):
    combined = reduce(lambda left, right: left.merge(right, on=["player_id", "player", "team"], how="outer"), frames)
    stat_columns = [column for column in combined.columns if column not in {"player_id", "player", "team"}]
    combined[stat_columns] = combined[stat_columns].fillna(0)
    return combined


@lru_cache(maxsize=64)
def _category_data(season, group):
    raw = _raw_season(season)
    fbs_teams = set(raw.loc[raw["conference"].isin(FBS_CONFERENCES), "team"].dropna())
    data = raw.loc[raw["team"].isin(fbs_teams)].copy()
    if group == "passing":
        completions = _event(data, "completion_player_id", "completion_player", "completions")
        passing_yards = _event(data, "completion_player_id", "completion_player", "passing_yards", "completion_yds")
        passing_tds = _event(data, "completion_player_id", "completion_player", "passing_tds", mask=(data["touchdown_stat"].fillna(0) > 0) & data["reception_player"].notna())
        attempt_rows = pd.concat([
            data[["completion_player_id", "completion_player", "team"]].set_axis(["player_id", "player", "team"], axis=1),
            data[["incompletion_player_id", "incompletion_player", "team"]].set_axis(["player_id", "player", "team"], axis=1),
            data[["interception_thrown_player_id", "interception_thrown_player", "team"]].set_axis(["player_id", "player", "team"], axis=1),
        ]).dropna(subset=["player"])
        attempts = attempt_rows.groupby(["player_id", "player", "team"], as_index=False).size().rename(columns={"size": "attempts"})
        interceptions = _event(data, "interception_thrown_player_id", "interception_thrown_player", "interceptions_thrown")
        return _combine([passing_yards, passing_tds, completions, attempts, interceptions])
    if group == "rushing":
        return _combine([
            _event(data, "rush_player_id", "rush_player", "rushing_yards", "rush_yds"),
            _event(data, "rush_player_id", "rush_player", "rushing_tds", mask=(data["touchdown_stat"].fillna(0) > 0) & (data["touchdown_player_id"] == data["rush_player_id"])),
            _event(data, "rush_player_id", "rush_player", "carries"),
        ])
    if group == "receiving":
        return _combine([
            _event(data, "reception_player_id", "reception_player", "receiving_yards", "reception_yds"),
            _event(data, "reception_player_id", "reception_player", "receiving_tds", mask=(data["touchdown_stat"].fillna(0) > 0) & (data["touchdown_player_id"] == data["reception_player_id"])),
            _event(data, "reception_player_id", "reception_player", "receptions"),
        ])
    if group == "defense":
        defense = _combine([
            _event(raw, "interception_player_id", "interception_player", "interceptions", "interception_stat", team="opponent"),
            _event(raw, "sack_player_id", "sack_player", "sacks", "sack_stat", team="opponent"),
            _event(raw, "fumble_forced_player_id", "fumble_forced_player", "forced_fumbles", "fumble_forced_stat", team="opponent"),
            _event(raw, "pass_breakup_player_id", "pass_breakup_player", "pass_breakups", "pass_breakup_stat", team="opponent"),
        ])
        return defense.loc[defense["team"].isin(fbs_teams)].copy()
    return _combine([
        _event(data, "field_goal_made_player_id", "field_goal_made_player", "field_goals_made", "field_goal_made_stat"),
        _event(data, "field_goal_attempt_player_id", "field_goal_attempt_player", "field_goals_attempted", "field_goal_attempt_stat"),
    ])


def get_leaders(season, group, stat_key, limit=10):
    data = _official_rushing_data(season) if group == "rushing" else _category_data(season, group)
    if data.empty:
        return []
    leaders = data.loc[data[stat_key] > 0].sort_values(stat_key, ascending=False).head(limit)
    return [{"name": row["player"], "team": row["team"], "value": f'{row[stat_key]:,.0f}',
             "sortable_value": float(row[stat_key])} for _, row in leaders.iterrows()]


@lru_cache(maxsize=64)
def get_player_names(season, group):
    data = _official_rushing_data(season) if group == "rushing" else _category_data(season, group)
    return tuple(sorted(set(data["player"].dropna()), key=str.casefold))
