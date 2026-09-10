import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import requests

import nba_tracking_warehouse as warehouse
from scripts import build_nba_tracking_warehouse as builder


def player_payload(game="0022400001", kind="player_track"):
    stats = {field: 0 for field in (warehouse.TRACK_FIELDS if kind == "player_track" else warehouse.HUSTLE_FIELDS)}
    stats.update({"minutes": "20:30", "reboundChancesTotal": 8, "reboundChancesOffensive": 3,
                  "reboundChancesDefensive": 5, "contestedFieldGoalsMade": 2,
                  "contestedFieldGoalsAttempted": 5, "defendedAtRimFieldGoalsMade": 1,
                  "defendedAtRimFieldGoalsAttempted": 3, "screenAssists": 4})
    root = "boxScorePlayerTrack" if kind == "player_track" else "boxScoreHustle"
    player = {"personId": 11, "firstName": "Test", "familyName": "Player", "statistics": stats}
    return {root: {"gameId": game, "homeTeam": {"teamId": 1, "players": [player]},
                   "awayTeam": {"teamId": 2, "players": [{**player, "personId": 12}]}}}


def matchup_payload(game="0022400001"):
    stats = {field: 0 for field in warehouse.MATCHUP_FIELDS}
    stats.update({"partialPossessions": 10, "matchupMinutesSort": 120, "matchupFieldGoalsMade": 2,
                  "matchupFieldGoalsAttempted": 6, "helpFieldGoalsMade": 1, "helpFieldGoalsAttempted": 2})
    defender = {"personId": 22, "firstName": "Defensive", "familyName": "Player",
                "matchups": [{"personId": 33, "statistics": stats}]}
    return {"boxScoreMatchups": {"gameId": game, "homeTeam": {"players": [defender]}, "awayTeam": {"players": []}}}


class TrackingWarehouseTests(unittest.TestCase):
    def test_player_track_ingestion_and_raw_components(self):
        rows = warehouse.validate_payload(player_payload(), "0022400001", "player_track")
        self.assertEqual(rows[0]["reboundChancesTotal"], 8)
        self.assertAlmostEqual(rows[0]["minutes"], 20.5)
        self.assertEqual(rows[0]["source"], "NBA boxscoreplayertrackv3")

    def test_matchup_keeps_offense_and_defense_direction(self):
        row = warehouse.validate_payload(matchup_payload(), "0022400001", "matchups")[0]
        self.assertEqual(row["defensive_player_id"], "22")
        self.assertEqual(row["offensive_player_id"], "33")

    def test_hustle_screen_assist_ingestion(self):
        row = warehouse.validate_payload(player_payload(kind="hustle"), "0022400001", "hustle")[0]
        self.assertEqual(row["screenAssists"], 4)

    def test_attempt_validation(self):
        payload = player_payload()
        payload["boxScorePlayerTrack"]["homeTeam"]["players"][0]["statistics"]["contestedFieldGoalsMade"] = 9
        with self.assertRaises(ValueError): warehouse.validate_payload(payload, "0022400001", "player_track")

    def test_html_response_is_rejected_and_not_cached(self):
        response = Mock(status_code=200, headers={"content-type": "text/html"}, text="<html>blocked</html>")
        response.raise_for_status.return_value = None
        session = Mock(); session.get.return_value = response
        with self.assertRaises(RuntimeError): builder.fetch(session, "0022400001", "player_track", retries=0)

    def test_incremental_cache_and_multiseason_raw_aggregation(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            warehouse.save_validated(player_payload("0022400001"), "0022400001", 2025, "player_track", folder)
            warehouse.save_validated(player_payload("0022300001"), "0022300001", 2024, "player_track", folder)
            result = warehouse.aggregate(folder)
            self.assertAlmostEqual(result["players"]["11"]["player_track"]["reboundChancesTotal"], 8 * 1.65)
            self.assertEqual(result["players"]["11"]["player_track"]["unique_games"], 2)
            self.assertEqual(result["coverage"]["player_track"]["games_downloaded"], 2)

    def test_failed_request_resume_preserves_existing_cache(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            path = warehouse.cache_path("0022400001", "player_track", folder)
            warehouse.save_validated(player_payload(), "0022400001", 2025, "player_track", folder)
            before = path.read_text()
            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(), before)


if __name__ == "__main__": unittest.main()
