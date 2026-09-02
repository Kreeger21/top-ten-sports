import unittest
from unittest.mock import patch
import pandas as pd

from app import app
from mlb_service import STAT_OPTIONS, get_leaders, get_player_names


FAKE_RESPONSE = {
    "stats": [
        {
            "splits": [
                {"player": {"fullName": "Second"}, "team": {"name": "B"}, "stat": {"avg": ".300", "era": "2.50"}},
                {"player": {"fullName": "First"}, "team": {"name": "A"}, "stat": {"avg": ".350", "era": "1.90"}},
            ]
        }
    ]
}


class LeaderTests(unittest.TestCase):
    @patch("mlb_service._fetch_stats", return_value=FAKE_RESPONSE)
    def test_average_sorts_high_to_low(self, _fetch):
        self.assertEqual(get_leaders(2025, "hitting", "avg")[0]["name"], "First")

    @patch("mlb_service._fetch_stats", return_value=FAKE_RESPONSE)
    def test_era_sorts_low_to_high(self, _fetch):
        self.assertEqual(get_leaders(2025, "pitching", "era")[0]["name"], "First")

    @patch("mlb_service._get_war_leaders", return_value=[{"name": "WAR Leader"}])
    def test_war_uses_separate_data_source(self, war_leaders):
        result = get_leaders(2025, "hitting", "war")
        self.assertEqual(result[0]["name"], "WAR Leader")
        war_leaders.assert_called_once_with(2025, "hitting", 10)

    def test_batting_and_pitching_war_have_distinct_labels(self):
        self.assertEqual(STAT_OPTIONS["hitting"]["war"]["label"], "Batting WAR")
        self.assertEqual(STAT_OPTIONS["pitching"]["war"]["label"], "Pitching WAR")

    def test_homepage_renders(self):
        response = app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"MLB Top Ten", response.data)
        self.assertIn(b"NFL Top Ten", response.data)
        self.assertIn(b"NBA Top Ten", response.data)

    def test_mlb_home_renders(self):
        response = app.test_client().get("/mlb")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Build Your Own", response.data)
        self.assertIn(b"Surprise Me", response.data)

    @patch("mlb_service.get_leaders", return_value=[])
    def test_leaderboard_renders(self, _leaders):
        response = app.test_client().get("/mlb/leaderboard?season=2025&group=hitting&stat=avg")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Batting Average Leaders", response.data)

    def test_random_choice_redirects_to_leaderboard(self):
        response = app.test_client().get("/mlb/random")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/mlb/leaderboard?", response.headers["Location"])
        self.assertIn("randomized=1", response.headers["Location"])

    @patch("mlb_service.get_leaders", return_value=[])
    def test_randomized_screen_has_respin_button(self, _leaders):
        response = app.test_client().get(
            "/mlb/leaderboard?season=1990&group=hitting&stat=stolenBases&randomized=1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Respin", response.data)
        self.assertIn(b"Your randomized leaderboard", response.data)

    @patch("mlb_service.get_leaders", return_value=[
        {"name": "Aaron Judge", "team": "New York Yankees", "value": "50"},
        {"name": "Shohei Ohtani", "team": "Los Angeles Dodgers", "value": "45"},
    ])
    def test_challenge_reveals_correct_guess(self, _leaders):
        client = app.test_client()
        response = client.post(
            "/mlb/challenge",
            data={"season": 2025, "group": "hitting", "stat": "homeRuns", "player": "judge"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Correct", response.data)
        self.assertIn(b"Aaron Judge", response.data)
        self.assertNotIn(b"Shohei Ohtani", response.data)

    @patch("mlb_service.get_leaders", return_value=[
        {"name": "Aaron Judge", "team": "NYY", "value": "50"},
        {"name": "Shohei Ohtani", "team": "LAD", "value": "45"},
    ])
    def test_forfeit_reveals_answers_and_score(self, _leaders):
        client = app.test_client()
        client.post("/mlb/challenge", data={"season": 2025, "group": "hitting", "stat": "homeRuns", "player": "Judge"})
        response = client.post("/mlb/challenge", data={"season": 2025, "group": "hitting", "stat": "homeRuns", "action": "forfeit"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Final score", response.data)
        self.assertIn(b"1/2", response.data)
        self.assertIn(b"Shohei Ohtani", response.data)
        self.assertIn(b"forfeited-player", response.data)

    @patch("mlb_service.get_leaders", return_value=[])
    def test_challenge_page_renders(self, _leaders):
        response = app.test_client().get("/mlb/challenge?season=2025&group=hitting&stat=homeRuns")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Who made the list?", response.data)
        self.assertIn(b"New Challenge", response.data)
        self.assertIn(b"guessInput.form.requestSubmit()", response.data)

    @patch("mlb_service.get_player_names", return_value=("Aaron Judge", "Arson Judge", "Shohei Ohtani"))
    def test_player_search_filters_names(self, _names):
        response = app.test_client().get("/mlb/api/player-search?season=2025&group=hitting&q=aaro")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), ["Aaron Judge"])

    @patch("mlb_service._fetch_stats", return_value=FAKE_RESPONSE)
    def test_player_names_are_collected_for_autocomplete(self, _fetch):
        self.assertEqual(get_player_names(2025, "hitting"), ("First", "Second"))

    def test_nfl_home_renders(self):
        response = app.test_client().get("/nfl")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"NFL Top Ten", response.data)

    @patch("nfl_service.get_leaders", return_value=[{"name": "Tom Brady", "team": "NE", "value": "5,000"}])
    def test_nfl_leaderboard_renders(self, _leaders):
        response = app.test_client().get("/nfl/leaderboard?season=2020&group=passing&stat=passing_yards")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Passing Yards Leaders", response.data)
        self.assertIn(b"Tom Brady", response.data)

    @patch("nfl_service._season_data")
    def test_nfl_leaders_are_sorted(self, season_data):
        from nfl_service import get_leaders as get_nfl_leaders
        season_data.return_value = pd.DataFrame([
            {"player_display_name": "Second", "team": "B", "passing_yards": 4000},
            {"player_display_name": "First", "team": "A", "passing_yards": 5000},
        ])
        self.assertEqual(get_nfl_leaders(2020, "passing", "passing_yards")[0]["name"], "First")

    def test_nba_home_renders(self):
        response = app.test_client().get("/nba")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"NBA Top Ten", response.data)

    @patch("nba_service.get_leaders", return_value=[{"name": "Nikola Jokic", "team": "DEN", "value": "29.6"}])
    def test_nba_leaderboard_renders(self, _leaders):
        response = app.test_client().get("/nba/leaderboard?season=2023&group=scoring&stat=PTS")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Points Per Game Leaders", response.data)
        self.assertIn(b"Nikola Jokic", response.data)

    @patch("nba_service._fetch_leaders", return_value=[
        {"PLAYER": "Second", "TEAM": "B", "PTS": 25.0},
        {"PLAYER": "First", "TEAM": "A", "PTS": 30.0},
    ])
    def test_nba_leaders_are_sorted(self, _fetch):
        from nba_service import get_leaders as get_nba_leaders
        self.assertEqual(get_nba_leaders(2023, "scoring", "PTS")[0]["name"], "First")

    @patch("nba_service._fetch_leaders", return_value=[
        {"PLAYER": "Qualified", "TEAM": "A", "GP": 70, "PTS": 20.0},
        {"PLAYER": "Too Few Games", "TEAM": "B", "GP": 20, "PTS": 40.0},
    ])
    def test_nba_minimum_games_filter(self, _fetch):
        from nba_service import get_leaders as get_nba_leaders
        result = get_nba_leaders(2023, "scoring", "PTS", min_games=50)
        self.assertEqual([player["name"] for player in result], ["Qualified"])

    @patch("nba_service.get_leaders", return_value=[])
    def test_nba_fixed_minimum_games_renders(self, leaders):
        response = app.test_client().get("/nba/leaderboard?season=2023&group=scoring&stat=PTS&min_games=55")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"at least 65 games", response.data)
        self.assertNotIn(b'name="min_games"', response.data)
        leaders.assert_called_once_with(2023, "scoring", "PTS", min_games=65)


if __name__ == "__main__":
    unittest.main()
