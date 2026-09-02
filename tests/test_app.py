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
        self.assertIn(b"FBS Top Ten", response.data)

    def test_mlb_home_renders(self):
        response = app.test_client().get("/mlb")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Build Your Own", response.data)
        self.assertIn(b"Surprise Me", response.data)
        self.assertIn(b"Award Winners", response.data)
        self.assertIn(b"WAR Diamond", response.data)

    @patch("war_diamond_service.get_player_names", return_value=("Hank Aaron", "Dale Murphy"))
    @patch("war_diamond_service.get_lineup", return_value=[
        {"position": "RF", "name": "Hank Aaron", "season": 1961, "war": 9.5, "team": "Atlanta Braves"},
        {"position": "P", "name": "Greg Maddux", "season": 1995, "war": 9.7, "team": "Atlanta Braves"},
    ])
    def test_war_diamond_reveals_correct_position(self, _lineup, _names):
        response = app.test_client().post(
            "/mlb/war-diamond", data={"team": "ATL", "era": "modern", "player": "Hank Aaron"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Hank Aaron", response.data)
        self.assertIn(b"1961", response.data)
        self.assertIn(b"9.5 WAR", response.data)
        _lineup.assert_called_once_with("ATL", "medium")

    @patch("war_diamond_service.get_player_names", return_value=("Hank Aaron", "Dale Murphy"))
    @patch("war_diamond_service.get_lineup", return_value=[
        {"position": "RF", "name": "Hank Aaron", "season": 1961, "war": 9.5, "team": "Atlanta Braves"},
        {"position": "DH", "name": "Marcell Ozuna", "season": 2024, "war": 4.5, "team": "Atlanta Braves"},
    ])
    def test_war_diamond_has_era_choice_and_full_team_roster(self, _lineup, _names):
        response = app.test_client().get("/mlb/war-diamond?team=ATL&era=hard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="era-select"', response.data)
        self.assertIn(b'value="easy"', response.data)
        self.assertIn(b'value="medium"', response.data)
        self.assertIn(b'value="hard" selected', response.data)
        self.assertIn(b"Dale Murphy", response.data)
        self.assertIn(b"pos-dh", response.data)
        _lineup.assert_called_once_with("ATL", "hard")
        _names.assert_called_once_with("ATL", "hard")

    def test_war_diamond_difficulty_year_ranges_and_dh(self):
        from war_diamond_service import POSITION_COLUMNS, _in_era
        seasons = pd.DataFrame({"year_ID": [1900, 1901, 1949, 1950, 2025]})
        self.assertEqual(_in_era(seasons, "easy")["year_ID"].tolist(), [1950, 2025])
        self.assertEqual(_in_era(seasons, "medium")["year_ID"].tolist(), [1901, 1949, 1950, 2025])
        self.assertEqual(_in_era(seasons, "hard")["year_ID"].tolist(), [1900, 1901, 1949, 1950, 2025])
        self.assertEqual(POSITION_COLUMNS["DH"], "G_dh")

    def test_war_diamond_preserves_scroll_after_guess(self):
        with open("templates/war_diamond.html", encoding="utf-8") as template_file:
            template = template_file.read()
        self.assertIn("diamond-scroll", template)
        self.assertIn("sessionStorage.setItem", template)
        self.assertIn("preventScroll:true", template)

    def test_war_uses_conventional_half_up_rounding(self):
        from war_diamond_service import _round_war
        self.assertEqual(_round_war(9.45), 9.5)

    @patch("awards_service.get_player_names", return_value=("LeBron James", "Stephen Curry"))
    @patch("awards_service.get_decade_winners", return_value=[
        {"season": 2014, "season_label": "2014-15", "name": "Stephen Curry", "team": "Golden State Warriors"},
        {"season": 2015, "season_label": "2015-16", "name": "Stephen Curry", "team": "Golden State Warriors"},
        {"season": 2016, "season_label": "2016-17", "name": "LeBron James", "team": "Cleveland Cavaliers"},
    ])
    @patch("awards_service.get_decades", return_value=(2020, 2010, 2000))
    def test_award_game_reveals_every_season_for_repeat_winner(self, _decades, _winners, _names):
        client = app.test_client()
        response = client.post("/nba/awards", data={"decade": 2010, "player": "Stephen Curry"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"2 winning seasons", response.data)
        self.assertIn(b"2/3", response.data)
        self.assertIn(b"2010\xe2\x80\x932019", response.data)

    @patch("awards_service.get_player_names", return_value=("LeBron James",))
    @patch("awards_service.get_decade_winners", return_value=[
        {"season": 2016, "season_label": "2016-17", "name": "LeBron James", "team": "Cleveland Cavaliers"},
    ])
    @patch("awards_service.get_decades", return_value=(2010,))
    def test_award_game_forfeit_shows_final_score(self, _decades, _winners, _names):
        response = app.test_client().post("/nba/awards", data={"decade": 2010, "action": "forfeit"})
        self.assertIn(b"Final score", response.data)
        self.assertIn(b"forfeited-player", response.data)

    @patch("awards_service.get_player_names", return_value=("LeBron James",))
    @patch("awards_service.get_decade_winners", return_value=[
        {"season": 2016, "season_label": "2016-17", "name": "LeBron James", "team": "Cleveland Cavaliers"},
    ])
    @patch("awards_service.get_decades", return_value=(2010,))
    def test_award_guess_preserves_scroll_position(self, _decades, _winners, _names):
        response = app.test_client().get("/nba/awards?decade=2010")
        self.assertIn(b"sessionStorage.setItem(scrollKey", response.data)
        self.assertIn(b"preventScroll: true", response.data)
        self.assertIn(b'id="award-select"', response.data)

    def test_major_and_postseason_awards_are_available(self):
        from awards_service import AWARDS
        self.assertIn("dpoy", AWARDS["nfl"])
        self.assertIn("opoy", AWARDS["nfl"])
        self.assertIn("rookie", AWARDS["nba"])
        self.assertIn("world_series_mvp", AWARDS["mlb"])
        self.assertIn("super_bowl_mvp", AWARDS["nfl"])
        self.assertIn("finals_mvp", AWARDS["nba"])

    @patch("mlb_service.get_leaders", return_value=[])
    def test_leaderboard_renders(self, _leaders):
        response = app.test_client().get("/mlb/leaderboard?season=2025&group=hitting&stat=avg")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Batting Average Leaders", response.data)

    def test_random_setup_renders_parameter_controls(self):
        response = app.test_client().get("/mlb/random")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Customize Your Surprise", response.data)
        self.assertIn(b'name="min_year"', response.data)
        self.assertIn(b'name="max_year"', response.data)
        self.assertIn(b'name="groups"', response.data)
        self.assertIn(b'name="stats"', response.data)

    def test_random_choice_redirects_to_leaderboard(self):
        response = app.test_client().post("/mlb/random", data={
            "min_year": 2000, "max_year": 2025, "groups": "hitting", "stats": "hitting:avg"
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/mlb/leaderboard?", response.headers["Location"])
        self.assertIn("randomized=1", response.headers["Location"])
        self.assertIn("min_year=2000", response.headers["Location"])
        self.assertIn("groups=hitting", response.headers["Location"])

    @patch("mlb_service.get_leaders", return_value=[])
    def test_randomized_screen_has_respin_button(self, _leaders):
        response = app.test_client().get(
            "/mlb/leaderboard?season=1990&group=hitting&stat=stolenBases&randomized=1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Respin", response.data)
        self.assertIn(b"Your randomized leaderboard", response.data)
        self.assertIn(b"locked-controls", response.data)
        self.assertNotIn(b'id="season-select"', response.data)

    def test_random_parameters_require_category_and_statistic(self):
        response = app.test_client().post("/nba/random", data={"min_year": 2000, "max_year": 2025})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Select at least one category and one statistic", response.data)

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

    def test_college_football_home_renders(self):
        response = app.test_client().get("/college-football")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"College Football Top Ten", response.data)

    @patch("cfb_service.get_leaders", return_value=[{"name": "Player One", "team": "Georgia", "value": "4,000"}])
    def test_college_football_leaderboard_renders(self, _leaders):
        response = app.test_client().get(
            "/college-football/leaderboard?season=2024&group=passing&stat=passing_yards"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Passing Yards Leaders", response.data)
        self.assertIn(b"Player One", response.data)

    @patch("cfb_service._category_data", return_value=pd.DataFrame([
        {"player": "Second", "team": "Team B", "passing_yards": 3500},
        {"player": "First", "team": "Team A", "passing_yards": 4200},
    ]))
    def test_college_football_leaders_are_sorted(self, _data):
        from cfb_service import get_leaders as get_cfb_leaders
        self.assertEqual(get_cfb_leaders(2024, "passing", "passing_yards")[0]["name"], "First")

    @patch("cfb_service._official_rushing_data", return_value=pd.DataFrame([
        {"player": "Second", "team": "Team B", "rushing_yards": 1900},
        {"player": "First", "team": "Team A", "rushing_yards": 2200},
    ]))
    def test_college_football_rushing_uses_official_totals(self, official_data):
        from cfb_service import get_leaders as get_cfb_leaders
        leaders = get_cfb_leaders(2017, "rushing", "rushing_yards")
        self.assertEqual(leaders[0]["name"], "First")
        self.assertEqual(leaders[0]["value"], "2,200")
        official_data.assert_called_once_with(2017)

    def test_college_football_does_not_offer_unreliable_targets(self):
        from cfb_service import STAT_OPTIONS as cfb_options
        self.assertNotIn("targets", cfb_options["receiving"])

    @patch("cfb_service.pd.read_csv", return_value=pd.DataFrame())
    def test_college_football_only_loads_required_columns(self, read_csv):
        from cfb_service import _raw_season
        _raw_season.cache_clear()
        _raw_season(2022)
        usecols = read_csv.call_args.kwargs["usecols"]
        self.assertTrue(usecols("rush_yds"))
        self.assertFalse(usecols("play_text"))

    @patch("cfb_service.get_leaders", return_value=[])
    def test_season_is_a_dropdown(self, _leaders):
        response = app.test_client().get("/college-football/leaderboard?season=2017&group=rushing&stat=rushing_yards")
        self.assertIn(b'<select name="season" id="season-select"', response.data)
        self.assertNotIn(b'<input type="number" name="season"', response.data)

    @patch("cfb_service.get_leaders", return_value=[])
    def test_historical_cfb_rushing_is_available(self, leaders):
        response = app.test_client().get("/college-football/leaderboard?season=1996&group=rushing&stat=rushing_yards")
        self.assertEqual(response.status_code, 200)
        leaders.assert_called_once_with(1996, "rushing", "rushing_yards")

    @patch("cfb_service.get_leaders", return_value=[])
    def test_unsupported_historical_cfb_stat_falls_back_to_rushing(self, leaders):
        app.test_client().get("/college-football/leaderboard?season=2005&group=passing&stat=passing_yards")
        leaders.assert_called_once_with(2005, "rushing", "rushing_yards")


if __name__ == "__main__":
    unittest.main()
