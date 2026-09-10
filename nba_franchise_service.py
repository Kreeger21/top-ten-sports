"""NBA franchise simulation rules and deterministic 82-game schedule model."""

from dataclasses import dataclass
import csv
from functools import lru_cache
from pathlib import Path
from random import Random

import nba_attribute_service


DATA_SNAPSHOT = "2026 offseason"
RULES_SEASON = "2026–27"

FINANCIAL_RULES = {
    "salary_cap": 164_961_000,
    "minimum_team_salary": 148_465_000,
    "luxury_tax": 200_428_000,
    "first_apron": 209_015_000,
    "second_apron": 221_686_000,
    "non_taxpayer_mle": 15_044_000,
    "taxpayer_mle": 6_064_000,
    "room_mle": 9_366_000,
}

ROSTER_RULES = {
    "standard_max": 15,
    "standard_min": 14,
    "active_max": 13,
    "active_min": 8,
    "two_way_max": 3,
}

POSTSEASON_RULES = {
    "automatic_seeds": 6,
    "play_in_seeds": (7, 8, 9, 10),
    "playoff_teams_per_conference": 8,
    "series_best_of": 7,
    "home_format": "2-2-1-1-1",
}

SCHEDULE_RULES = {"total_games": 82, "published_games": 80, "nba_cup_assigned_games": 2}


@dataclass(frozen=True)
class Team:
    code: str
    name: str
    city: str
    conference: str
    division: str


_TEAM_ROWS = (
    ("BOS", "Celtics", "Boston", "East", "Atlantic"), ("BKN", "Nets", "Brooklyn", "East", "Atlantic"),
    ("NYK", "Knicks", "New York", "East", "Atlantic"), ("PHI", "76ers", "Philadelphia", "East", "Atlantic"),
    ("TOR", "Raptors", "Toronto", "East", "Atlantic"), ("CHI", "Bulls", "Chicago", "East", "Central"),
    ("CLE", "Cavaliers", "Cleveland", "East", "Central"), ("DET", "Pistons", "Detroit", "East", "Central"),
    ("IND", "Pacers", "Indiana", "East", "Central"), ("MIL", "Bucks", "Milwaukee", "East", "Central"),
    ("ATL", "Hawks", "Atlanta", "East", "Southeast"), ("CHA", "Hornets", "Charlotte", "East", "Southeast"),
    ("MIA", "Heat", "Miami", "East", "Southeast"), ("ORL", "Magic", "Orlando", "East", "Southeast"),
    ("WAS", "Wizards", "Washington", "East", "Southeast"), ("DEN", "Nuggets", "Denver", "West", "Northwest"),
    ("MIN", "Timberwolves", "Minnesota", "West", "Northwest"), ("OKC", "Thunder", "Oklahoma City", "West", "Northwest"),
    ("POR", "Trail Blazers", "Portland", "West", "Northwest"), ("UTA", "Jazz", "Utah", "West", "Northwest"),
    ("GSW", "Warriors", "Golden State", "West", "Pacific"), ("LAC", "Clippers", "LA", "West", "Pacific"),
    ("LAL", "Lakers", "Los Angeles", "West", "Pacific"), ("PHX", "Suns", "Phoenix", "West", "Pacific"),
    ("SAC", "Kings", "Sacramento", "West", "Pacific"), ("DAL", "Mavericks", "Dallas", "West", "Southwest"),
    ("HOU", "Rockets", "Houston", "West", "Southwest"), ("MEM", "Grizzlies", "Memphis", "West", "Southwest"),
    ("NOP", "Pelicans", "New Orleans", "West", "Southwest"), ("SAS", "Spurs", "San Antonio", "West", "Southwest"),
)
TEAMS = tuple(Team(*row) for row in _TEAM_ROWS)
TEAM_BY_CODE = {team.code: team for team in TEAMS}
ROSTER_PATH = Path(__file__).with_name("data") / "nba_franchise_rosters.csv"
STATS_PATH = Path(__file__).with_name("data") / "nba_franchise_stats_2025.csv"
STAT_OPTIONS = {
    "g": "GP", "pts": "PTS", "trb": "REB", "ast": "AST",
    "stl": "STL", "blk": "BLK", "x3p": "3PM",
}
STATS_TEAM_CODES = {"BKN": "BRK", "CHA": "CHO", "PHX": "PHO"}


@lru_cache(maxsize=1)
def _roster_rows():
    if not ROSTER_PATH.exists():
        return ()
    with ROSTER_PATH.open(encoding="utf-8") as handle:
        return tuple(csv.DictReader(handle))


@lru_cache(maxsize=1)
def _stat_rows():
    if not STATS_PATH.exists():
        return ()
    with STATS_PATH.open(encoding="utf-8") as handle:
        return tuple(row for row in csv.DictReader(handle) if row.get("season") == "2025")


def statistics(team_code, mode="totals", view="team", limit=50):
    view = view if view in {"team", "league"} else "team"
    mode = mode if mode in {"totals", "per_game"} else "totals"
    rows = _stat_rows()
    if view == "team":
        rows = tuple(row for row in rows if row["team"] == STATS_TEAM_CODES.get(team_code, team_code))
    else:
        by_player = {}
        for row in rows:
            by_player.setdefault(row["player_id"], []).append(row)
        combined = []
        for player_rows in by_player.values():
            total_row = next((row for row in player_rows if row["team"] == "TOT"), None)
            if total_row:
                combined.append(total_row)
                continue
            base = dict(player_rows[0])
            for key in STAT_OPTIONS:
                base[key] = sum(float(row[key]) for row in player_rows if row.get(key))
            combined.append(base)
        rows = tuple(combined)
    ranked = sorted((row for row in rows if row.get("pts")),
                    key=lambda row: float(row["pts"]), reverse=True)[:limit]
    leaders = []
    for rank, row in enumerate(ranked, 1):
        games = float(row.get("g") or 0)
        values = {}
        for key in STAT_OPTIONS:
            raw = float(row.get(key) or 0)
            values[key] = round(raw / games, 1) if mode == "per_game" and key != "g" and games else int(raw)
        leaders.append({"rank": rank, "name": row["player"], "team": row["team"],
                        "position": row["pos"] or "—", "stats": values, "value": values["pts"]})
    return {"mode": mode, "view": view, "leaders": tuple(leaders)}


def roster(team_code):
    players = []
    for row in _roster_rows():
        if row["team"] != team_code:
            continue
        salary = int(float(row["salary_2026_27"])) if row["salary_2026_27"] else None
        remaining = int(float(row["years_remaining"])) if row["years_remaining"] else None
        players.append({**row, "age": int(float(row["age"])) if row["age"] else None,
                        "salary": salary, "years_remaining": remaining,
                        "contract_verified": salary is not None,
                        "attribute_profile": nba_attribute_service.attributes_for_player(row["player_id"])})
    return tuple(sorted(players, key=lambda player: (player["position"], player["name"])))


def roster_player(team_code, player_id):
    """Return a player only when they belong to the selected franchise roster."""
    return next((player for player in roster(team_code) if player["player_id"] == str(player_id)), None)


def starting_lineup(team_code):
    """Return a balanced projected five without inventing unsupported positions."""
    players = roster(team_code)
    ranked = sorted(players, key=lambda player: (player["salary"] or 0, player["name"]), reverse=True)
    lineup = []
    used = set()
    for label, position in (("PG", "G"), ("SG", "G"), ("SF", "F"), ("PF", "F"), ("C", "C")):
        player = next((candidate for candidate in ranked
                       if candidate["position"] == position and candidate["player_id"] not in used), None)
        if player is None:
            player = next((candidate for candidate in ranked if candidate["player_id"] not in used), None)
        if player:
            used.add(player["player_id"])
            lineup.append({"slot": label, "name": player["name"]})
    return tuple(lineup)


def team_updates(team_code):
    team = TEAM_BY_CODE.get(team_code, TEAM_BY_CODE["ATL"])
    return (
        {"type": "Roster", "title": f"{team.city} offseason roster loaded",
         "detail": "Current player and position records are available for review."},
        {"type": "Contracts", "title": "Contract verification in progress",
         "detail": "Unavailable salary terms remain clearly marked and excluded from payroll."},
        {"type": "League", "title": "2026–27 rules are active",
         "detail": "Salary-cap, apron, roster, schedule, and postseason rules are enabled."},
    )


def _conference_order(conference):
    """Interleave divisions so symmetric offsets create six non-division rivals."""
    teams = [team for team in TEAMS if team.conference == conference]
    divisions = list(dict.fromkeys(team.division for team in teams))
    groups = [[team for team in teams if team.division == division] for division in divisions]
    return [groups[division][slot] for slot in range(5) for division in range(3)]


def opponent_counts(team_code):
    """Return the NBA 82-game opponent allocation for one team."""
    team = TEAM_BY_CODE[team_code]
    counts = {}
    conference = _conference_order(team.conference)
    index = conference.index(team)
    bonus = {conference[(index + offset) % 15].code for offset in (-4, -2, -1, 1, 2, 4)}
    for opponent in TEAMS:
        if opponent.code == team.code:
            continue
        if opponent.conference != team.conference:
            counts[opponent.code] = 2
        elif opponent.division == team.division:
            counts[opponent.code] = 4
        else:
            counts[opponent.code] = 4 if opponent.code in bonus else 3
    return counts


def regular_season_schedule(team_code, seed=2026):
    opponents = [code for code, count in opponent_counts(team_code).items() for _ in range(count)]
    Random(f"{seed}:{team_code}").shuffle(opponents)
    return tuple({"game": number, "opponent": code, "home": number % 2 == 1}
                 for number, code in enumerate(opponents, 1))


def team_overview(team_code):
    team = TEAM_BY_CODE.get(team_code, TEAM_BY_CODE["ATL"])
    players = roster(team.code)
    verified = [player for player in players if player["contract_verified"]]
    verified_payroll = sum(player["salary"] for player in verified)
    return {
        "team": team,
        "schedule": regular_season_schedule(team.code),
        "financial_rules": FINANCIAL_RULES,
        "roster_rules": ROSTER_RULES,
        "postseason_rules": POSTSEASON_RULES,
        "schedule_rules": SCHEDULE_RULES,
        "snapshot": DATA_SNAPSHOT,
        "rules_season": RULES_SEASON,
        "roster": players,
        "starting_lineup": starting_lineup(team.code),
        "current_week": regular_season_schedule(team.code)[:4],
        "team_updates": team_updates(team.code),
        "stats_preview": statistics(team.code, limit=3)["leaders"],
        "verified_contracts": len(verified),
        "verified_payroll": verified_payroll,
        "cap_balance": FINANCIAL_RULES["salary_cap"] - verified_payroll,
        "tax_balance": FINANCIAL_RULES["luxury_tax"] - verified_payroll,
        "first_apron_balance": FINANCIAL_RULES["first_apron"] - verified_payroll,
        "second_apron_balance": FINANCIAL_RULES["second_apron"] - verified_payroll,
        "tradeable_players": tuple(player for player in players if player["contract_verified"]),
        "draft_assets_verified": False,
        "snapshot_at": players[0]["snapshot_at"][:10] if players else None,
    }
