"""Refresh the NBA Franchise Mode roster snapshot from ESPN's public team feed."""

import csv
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "nba_franchise_rosters.csv"
ROSTER_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/roster"
TEAM_IDS = {
    "ATL": 1, "BOS": 2, "BKN": 17, "CHA": 30, "CHI": 4, "CLE": 5, "DAL": 6, "DEN": 7,
    "DET": 8, "GSW": 9, "HOU": 10, "IND": 11, "LAC": 12, "LAL": 13, "MEM": 29, "MIA": 14,
    "MIL": 15, "MIN": 16, "NOP": 3, "NYK": 18, "OKC": 25, "ORL": 19, "PHI": 20, "PHX": 21,
    "POR": 22, "SAC": 23, "SAS": 24, "TOR": 28, "UTA": 26, "WAS": 27,
}
FIELDS = (
    "snapshot_at", "team", "player_id", "name", "position", "jersey", "age", "birthdate",
    "status", "salary_2026_27", "years_remaining", "contract_end_year", "contract_type",
)


def _contract_end(athlete):
    seasons = [item.get("season", {}).get("year") for item in athlete.get("contracts", [])]
    seasons = [int(year) for year in seasons if year and int(year) >= 2027]
    return max(seasons, default=None)


def build():
    session = requests.Session()
    snapshot_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows = []
    for code, team_id in TEAM_IDS.items():
        response = session.get(ROSTER_URL.format(team_id=team_id), timeout=30)
        response.raise_for_status()
        for athlete in response.json().get("athletes", []):
            contract = athlete.get("contract") or {}
            season_contract = next((item for item in athlete.get("contracts", [])
                                    if item.get("season", {}).get("year") == 2027), {})
            rows.append({
                "snapshot_at": snapshot_at,
                "team": code,
                "player_id": athlete["id"],
                "name": athlete["displayName"],
                "position": athlete.get("position", {}).get("abbreviation", "—"),
                "jersey": athlete.get("jersey", ""),
                "age": athlete.get("age", ""),
                "birthdate": str(athlete.get("dateOfBirth", ""))[:10],
                "status": athlete.get("status", {}).get("name", "Active"),
                "salary_2026_27": season_contract.get("salary", contract.get("salary", "")),
                "years_remaining": contract.get("yearsRemaining", ""),
                "contract_end_year": _contract_end(athlete) or "",
                "contract_type": "Two-way" if contract.get("twoWay") else ("Standard" if season_contract.get("salary", contract.get("salary")) else "Unverified"),
            })
    rows.sort(key=lambda row: (row["team"], row["position"], row["name"]))
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} active player records across {len(TEAM_IDS)} teams to {OUTPUT}")


if __name__ == "__main__":
    build()
