"""Cache high-value player features from official NBA statistics endpoints.

This is an offline ingestion command. The web application never calls NBA.com.
The previous verified cache is preserved if any required request fails.
"""

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unicodedata

import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "nba_official_features.json"
BASE_STATS = ROOT / "data" / "nba_franchise_stats_2025.csv"
BASE_URL = "https://stats.nba.com/stats/"
SEASONS = ("2024-25", "2023-24", "2022-23")
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
}
COMMON = {"LeagueID": "00", "PerMode": "Totals", "SeasonType": "Regular Season", "LastNGames": 0,
          "Month": 0, "OpponentTeamID": 0, "PORound": 0, "Period": 0}

REQUESTS = (
    ("advanced", "leaguedashplayerstats", {"MeasureType": "Advanced", "PaceAdjust": "N", "PlusMinus": "N", "Rank": "N"}),
    ("hustle", "leaguehustlestatsplayer", {}),
    ("catch_shoot", "leaguedashptstats", {"PtMeasureType": "CatchShoot"}),
    ("pull_up", "leaguedashptstats", {"PtMeasureType": "PullUpShot"}),
    ("drives", "leaguedashptstats", {"PtMeasureType": "Drives"}),
    ("passing", "leaguedashptstats", {"PtMeasureType": "Passing"}),
    ("rebounding_tracking", "leaguedashptstats", {"PtMeasureType": "Rebounding"}),
)


def _normal(value):
    plain = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return " ".join(plain.casefold().split())


def _identity_by_name():
    matches = {}
    with BASE_STATS.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            matches.setdefault(_normal(row["player"]), set()).add(row["player_id"])
    return {name: next(iter(ids)) for name, ids in matches.items() if len(ids) == 1}


def _result_rows(payload):
    result = payload.get("resultSets") or payload.get("resultSet") or []
    if isinstance(result, dict): result = [result]
    if not result: return []
    first = result[0]
    headers = first.get("headers", [])
    return [dict(zip(headers, values)) for values in first.get("rowSet", [])]


def _request(session, endpoint, params, timeout):
    response = session.get(BASE_URL + endpoint, params=params, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return _result_rows(response.json())


def build(timeout=45):
    identities = _identity_by_name()
    players, source_log = {}, []
    with requests.Session() as session:
        for season in SEASONS:
            for prefix, endpoint, specific in REQUESTS:
                params = {**COMMON, **specific, "Season": season}
                rows = _request(session, endpoint, params, timeout)
                source_log.append({"endpoint": endpoint, "dataset": prefix, "season": season, "rows": len(rows)})
                season_weight = {"2024-25": 1.0, "2023-24": .65, "2022-23": .40}[season]
                for row in rows:
                    name = row.get("PLAYER_NAME") or row.get("PLAYER") or ""
                    stats_id = identities.get(_normal(name))
                    if not stats_id: continue
                    target = players.setdefault(stats_id, {"player": name, "seasons": {}})
                    target["seasons"].setdefault(season, {})[prefix] = row
                    target["season_weights"] = {**target.get("season_weights", {}), season: season_weight}
    return {"status": "verified", "schema_version": 1, "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "stats.nba.com", "sources": source_log, "players": players}


def _atomic_write(payload):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix="nba-official-", suffix=".json", dir=OUTPUT.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
        os.replace(temporary, OUTPUT)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()
    payload = build(args.timeout)
    _atomic_write(payload)
    print(f"Cached {len(payload['players']):,} verified NBA player feature profiles to {OUTPUT}")


if __name__ == "__main__":
    main()
