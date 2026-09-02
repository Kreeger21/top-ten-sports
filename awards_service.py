from functools import lru_cache
from io import StringIO
import re

from bs4 import BeautifulSoup
import pandas as pd
import requests


WIKI = "https://en.wikipedia.org/wiki/"
AWARDS = {
    "mlb": {
        "mvp": {"name": "Most Valuable Player", "short": "MVP", "url": WIKI + "Major_League_Baseball_Most_Valuable_Player_Award", "kind": "mlb_mvp"},
        "cy_young": {"name": "Cy Young Award", "short": "CY", "url": WIKI + "Cy_Young_Award", "tables": (3, 4), "player": "Pitcher"},
        "rookie": {"name": "Rookie of the Year", "short": "ROY", "url": WIKI + "Major_League_Baseball_Rookie_of_the_Year_Award", "tables": (3, 4)},
        "world_series_mvp": {"name": "World Series MVP", "short": "WS MVP", "url": WIKI + "World_Series_Most_Valuable_Player_Award", "tables": (2,)},
        "lcs_mvp": {"name": "League Championship Series MVP", "short": "LCS MVP", "url": WIKI + "League_Championship_Series_Most_Valuable_Player_Award", "tables": (2, 3)},
    },
    "nfl": {
        "mvp": {"name": "AP Most Valuable Player", "short": "MVP", "url": WIKI + "National_Football_League_Most_Valuable_Player_Award", "kind": "nfl_mvp"},
        "opoy": {"name": "Offensive Player of the Year", "short": "OPOY", "url": WIKI + "NFL_Offensive_Player_of_the_Year_Award", "tables": (0,), "player": "Associated Press"},
        "dpoy": {"name": "Defensive Player of the Year", "short": "DPOY", "url": WIKI + "NFL_Defensive_Player_of_the_Year_Award", "tables": (0,)},
        "rookie": {"name": "Offensive & Defensive Rookie of the Year", "short": "ROY", "url": WIKI + "NFL_Offensive_Rookie_of_the_Year_Award", "tables": (0,), "multi": ("Offensive Player", "Defensive Player")},
        "comeback": {"name": "Comeback Player of the Year", "short": "CPOY", "url": WIKI + "NFL_Comeback_Player_of_the_Year_Award", "tables": (2,)},
        "super_bowl_mvp": {"name": "Super Bowl MVP", "short": "SB MVP", "url": WIKI + "Super_Bowl_Most_Valuable_Player_Award", "tables": (2,), "player": "Winner"},
    },
    "nba": {
        "mvp": {"name": "Most Valuable Player", "short": "MVP", "url": WIKI + "NBA_Most_Valuable_Player_Award", "tables": (3,)},
        "dpoy": {"name": "Defensive Player of the Year", "short": "DPOY", "url": WIKI + "NBA_Defensive_Player_of_the_Year_Award", "tables": (3,)},
        "rookie": {"name": "Rookie of the Year", "short": "ROY", "url": WIKI + "NBA_Rookie_of_the_Year_Award", "tables": (3,)},
        "most_improved": {"name": "Most Improved Player", "short": "MIP", "url": WIKI + "NBA_Most_Improved_Player_Award", "tables": (3,)},
        "sixth_man": {"name": "Sixth Man of the Year", "short": "6MOY", "url": WIKI + "NBA_Sixth_Man_of_the_Year_Award", "tables": (3,)},
        "finals_mvp": {"name": "Finals MVP", "short": "FINALS MVP", "url": WIKI + "NBA_Finals_Most_Valuable_Player_Award", "tables": (3,)},
        "conference_finals_mvp": {"name": "Conference Finals MVP", "short": "CF MVP", "url": WIKI + "NBA_Conference_Finals_Most_Valuable_Player_Award", "tables": (3, 4)},
    },
    "cfb": {
        "heisman": {"name": "Heisman Trophy", "short": "HEISMAN", "url": "https://www.heisman.com/heisman-winners/", "kind": "heisman"},
        "maxwell": {"name": "Maxwell Award", "short": "MAXWELL", "url": WIKI + "Maxwell_Award", "tables": (1,), "team": "School"},
        "walter_camp": {"name": "Walter Camp Award", "short": "CAMP", "url": WIKI + "Walter_Camp_Award", "tables": (1,), "player": "Winner", "team": "School"},
        "bednarik": {"name": "Chuck Bednarik Award", "short": "BEDNARIK", "url": WIKI + "Chuck_Bednarik_Award", "tables": (2,), "team": "School"},
        "nagurski": {"name": "Bronko Nagurski Trophy", "short": "NAGURSKI", "url": WIKI + "Bronko_Nagurski_Trophy", "tables": (1,), "player": "Winner", "team": "School"},
        "doak_walker": {"name": "Doak Walker Award", "short": "DOAK", "url": WIKI + "Doak_Walker_Award", "tables": (2,), "player": "Winner", "team": "School"},
        "biletnikoff": {"name": "Biletnikoff Award", "short": "BILETNIKOFF", "url": WIKI + "Fred_Biletnikoff_Award", "tables": (1,), "player": "Winner"},
        "davey_obrien": {"name": "Davey O'Brien Award", "short": "O'BRIEN", "url": WIKI + "Davey_O%27Brien_Award", "tables": (2,), "team": "School"},
    },
}

HEADERS = {"User-Agent": "TopTenSports/1.0 (public sports trivia application)"}


def _clean(value):
    value = re.sub(r"\[[^]]*]", "", str(value)).strip()
    value = re.sub(r"\s*\(\d+\)\s*$", "", value)
    value = value.rstrip("*^†‡§#� ")
    return value or "—"


def _page(url):
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.content


def _flatten_columns(table):
    table = table.copy()
    table.columns = [" ".join(str(part) for part in column if str(part) != "nan") if isinstance(column, tuple) else str(column) for column in table.columns]
    return table


@lru_cache(maxsize=32)
def get_history(sport_key, award_key):
    definition = AWARDS[sport_key][award_key]
    content = _page(definition["url"])
    records = []

    if definition.get("kind") == "heisman":
        soup = BeautifulSoup(content, "html.parser")
        for heading in soup.find_all("h2", class_="page-title"):
            container = heading.find_parent("div", class_="row")
            match = re.search(r"\b(19|20)\d{2}\b", container.get_text(" ", strip=True) if container else "")
            if match:
                records.append({"season": int(match.group()), "season_label": match.group(),
                                "name": _clean(heading.get_text(" ", strip=True)), "team": "—"})
        return tuple(sorted(records, key=lambda row: (row["season"], row["name"])))

    tables = pd.read_html(StringIO(content.decode("utf-8", errors="replace")))
    if definition.get("kind") not in {"mlb_mvp", "nfl_mvp"}:
        for table_index in definition["tables"]:
            table = _flatten_columns(tables[table_index])
            season_column = next(column for column in table.columns if "season" in column.lower() or "year" in column.lower())
            player_columns = definition.get("multi") or (definition.get("player", "Player"),)
            for _, row in table.iterrows():
                match = re.search(r"\d{4}", str(row[season_column]))
                if not match:
                    continue
                year = int(match.group())
                for requested_column in player_columns:
                    player_column = next((column for column in table.columns if requested_column.lower() == column.lower()), None)
                    if not player_column or pd.isna(row[player_column]):
                        continue
                    name = _clean(row[player_column])
                    if name in {"—", "-", "nan"}:
                        continue
                    team_requested = definition.get("team", "Team")
                    team_column = next((column for column in table.columns if team_requested.lower() == column.lower()), None)
                    team = _clean(row[team_column]) if team_column else "—"
                    season_label = f"{year}–{str(year + 1)[-2:]}" if "season" in season_column.lower() and sport_key == "nba" else str(year)
                    records.append({"season": year, "season_label": season_label, "name": name, "team": team})
    elif sport_key == "nba":
        table = next(table for table in tables if "Season" in table.columns and "Player" in table.columns)
        for _, row in table.iterrows():
            match = re.search(r"\d{4}", str(row["Season"]))
            if match:
                year = int(match.group())
                records.append({"season": year, "season_label": f"{year}–{str(year + 1)[-2:]}",
                                "name": _clean(row["Player"]), "team": _clean(row["Team"])})
    elif definition.get("kind") == "nfl_mvp":
        table = next(table for table in tables if "Year" in table.columns and "AP" in table.columns)
        for _, row in table.iterrows():
            if pd.isna(row["AP"]) or not str(row["Year"]).isdigit():
                continue
            for winner in re.split(r"\s*/\s*|\s+and\s+", str(row["AP"])):
                name = _clean(winner)
                if name and name not in {"—", "-"}:
                    records.append({"season": int(row["Year"]), "season_label": str(row["Year"]),
                                    "name": name, "team": "—"})
    else:
        award_tables = [table for table in tables if "Year" in table.columns and "American League winner" in table.columns]
        for table in award_tables:
            for _, row in table.iterrows():
                if not str(row["Year"]).isdigit():
                    continue
                for league, winner_column, team_column in (
                    ("AL", "American League winner", "Team"),
                    ("NL", "National League winner", "Team.1"),
                ):
                    name = _clean(row[winner_column])
                    if name and name not in {"—", "-", "nan"}:
                        records.append({"season": int(row["Year"]), "season_label": f'{row["Year"]} {league}',
                                        "name": name, "team": _clean(row[team_column])})
    return tuple(sorted(records, key=lambda row: (row["season"], row["season_label"])))


def get_decades(sport_key, award_key):
    years = [row["season"] for row in get_history(sport_key, award_key)]
    return tuple(range(max(years) // 10 * 10, min(years) // 10 * 10 - 1, -10))


def get_decade_winners(sport_key, award_key, decade):
    return [dict(row) for row in get_history(sport_key, award_key) if decade <= row["season"] <= decade + 9]


def get_player_names(sport_key, award_key):
    return tuple(sorted({row["name"] for row in get_history(sport_key, award_key)}, key=str.casefold))
