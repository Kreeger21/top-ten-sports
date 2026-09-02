import json
from functools import lru_cache
from urllib.parse import urlencode
from urllib.request import Request, urlopen


MLB_STATS_URL = "https://statsapi.mlb.com/api/v1/stats"
MLB_PEOPLE_URL = "https://statsapi.mlb.com/api/v1/people"

STAT_OPTIONS = {
    "hitting": {
        "avg": {"label": "Batting Average", "short": "BA", "qualified": True},
        "homeRuns": {"label": "Home Runs", "short": "HR"},
        "rbi": {"label": "Runs Batted In", "short": "RBI"},
        "hits": {"label": "Hits", "short": "H"},
        "stolenBases": {"label": "Stolen Bases", "short": "SB"},
        "war": {"label": "Batting WAR", "short": "bWAR", "provider": "Baseball-Reference"},
    },
    "pitching": {
        "era": {"label": "Earned Run Average", "short": "ERA", "qualified": True, "lower": True},
        "wins": {"label": "Wins", "short": "W"},
        "strikeOuts": {"label": "Strikeouts", "short": "SO"},
        "whip": {"label": "WHIP", "short": "WHIP", "qualified": True, "lower": True},
        "saves": {"label": "Saves", "short": "SV"},
        "war": {"label": "Pitching WAR", "short": "pWAR", "provider": "Baseball-Reference"},
    },
}


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=128)
def _fetch_stats(season, group, qualified):
    params = urlencode(
        {
            "stats": "season",
            "group": group,
            "season": season,
            "playerPool": "QUALIFIED" if qualified else "ALL",
            "limit": 5000,
            "hydrate": "person,team",
        }
    )
    request = Request(
        f"{MLB_STATS_URL}?{params}",
        headers={"User-Agent": "MLB Top Ten educational web app"},
    )
    with urlopen(request, timeout=12) as response:
        return json.load(response)


@lru_cache(maxsize=32)
def _fetch_people_names(player_ids):
    params = urlencode({"personIds": ",".join(str(player_id) for player_id in player_ids)})
    request = Request(
        f"{MLB_PEOPLE_URL}?{params}",
        headers={"User-Agent": "MLB Top Ten educational web app"},
    )
    with urlopen(request, timeout=12) as response:
        people = json.load(response).get("people", [])
    return {person["id"]: person["fullName"] for person in people}


def get_leaders(season, group, stat_key, limit=10):
    definition = STAT_OPTIONS[group][stat_key]
    if stat_key == "war":
        return _get_war_leaders(season, group, limit)

    data = _fetch_stats(season, group, definition.get("qualified", False))
    splits = data.get("stats", [{}])[0].get("splits", [])

    leaders = []
    for split in splits:
        value = split.get("stat", {}).get(stat_key)
        sortable_value = _number(value)
        # The Stats API currently names this hydrated object ``player``;
        # accepting ``person`` as well keeps the parser tolerant of both forms.
        person = split.get("player") or split.get("person", {})
        if sortable_value is None or not person.get("fullName"):
            continue
        leaders.append(
            {
                "name": person["fullName"],
                "team": split.get("team", {}).get("name", "—"),
                "value": value,
                "sortable_value": sortable_value,
            }
        )

    leaders.sort(
        key=lambda player: player["sortable_value"],
        reverse=not definition.get("lower", False),
    )
    return leaders[:limit]


@lru_cache(maxsize=64)
def get_player_names(season, group):
    """Return every player with stats in a season/category for autocomplete."""
    data = _fetch_stats(season, group, False)
    splits = data.get("stats", [{}])[0].get("splits", [])
    names = {
        person["fullName"]
        for split in splits
        if (person := split.get("player") or split.get("person", {})).get("fullName")
    }
    return tuple(sorted(names, key=str.casefold))


@lru_cache(maxsize=32)
def _get_war_leaders(season, group, limit=10):
    # MLB's Stats API does not publish WAR. pybaseball's bWAR tables provide
    # Baseball-Reference WAR for completed seasons.
    from pybaseball import bwar_bat, bwar_pitch

    data = bwar_bat(return_all=True) if group == "hitting" else bwar_pitch(return_all=True)
    season_data = data.loc[data["year_ID"] == season, ["mlb_ID", "name_common", "team_ID", "WAR"]].copy()
    if season_data.empty:
        return []

    # A traded player can have multiple rows. Combine the stints into a single
    # season value and display all of the player's team abbreviations.
    season_data["team_ID"] = season_data["team_ID"].fillna("—").astype(str)
    combined = season_data.groupby(["mlb_ID", "name_common"], dropna=False).agg(
        WAR=("WAR", "sum"),
        team_ID=("team_ID", lambda teams: "/".join(dict.fromkeys(teams))),
    )
    combined = combined.reset_index().sort_values("WAR", ascending=False).head(limit)
    player_ids = tuple(int(player_id) for player_id in combined["mlb_ID"] if player_id == player_id)
    official_names = _fetch_people_names(player_ids) if player_ids else {}

    return [
        {
            "name": official_names.get(int(row["mlb_ID"]), row["name_common"]),
            "team": row["team_ID"],
            "value": f'{row["WAR"]:.1f}',
            "sortable_value": float(row["WAR"]),
        }
        for _, row in combined.iterrows()
    ]
