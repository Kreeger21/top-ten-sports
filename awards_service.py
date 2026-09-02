from functools import lru_cache
from io import StringIO
import re

from bs4 import BeautifulSoup
import pandas as pd
import requests


AWARDS = {
    "mlb": {
        "name": "Most Valuable Player",
        "short": "MVP",
        "url": "https://en.wikipedia.org/wiki/Major_League_Baseball_Most_Valuable_Player_Award",
    },
    "nfl": {
        "name": "AP Most Valuable Player",
        "short": "MVP",
        "url": "https://en.wikipedia.org/wiki/National_Football_League_Most_Valuable_Player_Award",
    },
    "nba": {
        "name": "Most Valuable Player",
        "short": "MVP",
        "url": "https://en.wikipedia.org/wiki/NBA_Most_Valuable_Player_Award",
    },
    "cfb": {
        "name": "Heisman Trophy",
        "short": "HEISMAN",
        "url": "https://www.heisman.com/heisman-winners/",
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


@lru_cache(maxsize=4)
def get_history(sport_key):
    definition = AWARDS[sport_key]
    content = _page(definition["url"])
    records = []

    if sport_key == "cfb":
        soup = BeautifulSoup(content, "html.parser")
        for heading in soup.find_all("h2", class_="page-title"):
            container = heading.find_parent("div", class_="row")
            match = re.search(r"\b(19|20)\d{2}\b", container.get_text(" ", strip=True) if container else "")
            if match:
                records.append({"season": int(match.group()), "season_label": match.group(),
                                "name": _clean(heading.get_text(" ", strip=True)), "team": "—"})
        return tuple(sorted(records, key=lambda row: (row["season"], row["name"])))

    tables = pd.read_html(StringIO(content.decode("utf-8", errors="replace")))
    if sport_key == "nba":
        table = next(table for table in tables if "Season" in table.columns and "Player" in table.columns)
        for _, row in table.iterrows():
            match = re.search(r"\d{4}", str(row["Season"]))
            if match:
                year = int(match.group())
                records.append({"season": year, "season_label": f"{year}–{str(year + 1)[-2:]}",
                                "name": _clean(row["Player"]), "team": _clean(row["Team"])})
    elif sport_key == "nfl":
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


def get_decades(sport_key):
    years = [row["season"] for row in get_history(sport_key)]
    return tuple(range(max(years) // 10 * 10, min(years) // 10 * 10 - 1, -10))


def get_decade_winners(sport_key, decade):
    return [dict(row) for row in get_history(sport_key) if decade <= row["season"] <= decade + 9]


def get_player_names(sport_key):
    return tuple(sorted({row["name"] for row in get_history(sport_key)}, key=str.casefold))
