import json
from functools import lru_cache
from urllib.parse import urlencode
from urllib.request import Request, urlopen


NBA_LEADERS_URL = "https://stats.nba.com/stats/leagueleaders"
MIN_SEASON = 1946

STAT_OPTIONS = {
    "scoring": {
        "PTS": {"label": "Points Per Game", "short": "PPG", "digits": 1},
        "FG3M": {"label": "Three-Pointers Made Per Game", "short": "3PM", "digits": 1},
        "FG_PCT": {"label": "Field Goal Percentage", "short": "FG%", "digits": 3},
        "FG3_PCT": {"label": "Three-Point Percentage", "short": "3P%", "digits": 3},
        "FT_PCT": {"label": "Free Throw Percentage", "short": "FT%", "digits": 3},
    },
    "rebounding": {
        "REB": {"label": "Rebounds Per Game", "short": "RPG", "digits": 1},
        "OREB": {"label": "Offensive Rebounds Per Game", "short": "OREB", "digits": 1},
        "DREB": {"label": "Defensive Rebounds Per Game", "short": "DREB", "digits": 1},
    },
    "playmaking": {
        "AST": {"label": "Assists Per Game", "short": "APG", "digits": 1},
        "AST_TOV": {"label": "Assist-to-Turnover Ratio", "short": "AST/TO", "digits": 2},
    },
    "defense": {
        "STL": {"label": "Steals Per Game", "short": "SPG", "digits": 1},
        "BLK": {"label": "Blocks Per Game", "short": "BPG", "digits": 1},
    },
}


def season_label(start_year):
    return f"{start_year}-{str(start_year + 1)[-2:]}"


@lru_cache(maxsize=128)
def _fetch_leaders(season, stat_key):
    params = urlencode({
        "LeagueID": "00",
        "PerMode": "PerGame",
        "Scope": "S",
        "Season": season_label(season),
        "SeasonType": "Regular Season",
        "StatCategory": stat_key,
    })
    request = Request(
        f"{NBA_LEADERS_URL}?{params}",
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.nba.com/"},
    )
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)["resultSet"]
    return [dict(zip(payload["headers"], row)) for row in payload["rowSet"]]


def get_leaders(season, group, stat_key, limit=10, min_games=0):
    definition = STAT_OPTIONS[group][stat_key]
    rows = _fetch_leaders(season, stat_key)
    eligible = [
        row for row in rows
        if row.get(stat_key) is not None and int(row.get("GP") or 0) >= min_games
    ]
    eligible.sort(key=lambda row: float(row[stat_key]), reverse=True)
    return [
        {
            "name": row["PLAYER"],
            "team": row.get("TEAM") or "—",
            "value": f'{float(row[stat_key]):.{definition["digits"]}f}',
            "sortable_value": float(row[stat_key]),
        }
        for row in eligible[:limit]
    ]


@lru_cache(maxsize=64)
def get_player_names(season, group):
    # Any category supplies the same season-wide player pool.
    rows = _fetch_leaders(season, "PTS")
    return tuple(sorted({row["PLAYER"] for row in rows if row.get("PLAYER")}, key=str.casefold))
