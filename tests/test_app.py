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
        self.assertIn(b"Quiz Your Friends", response.data)
        self.assertIn(b"Award Winners", response.data)
        self.assertIn(b"Fill the Field", response.data)

    @patch("war_diamond_service.get_player_names", return_value=("Hank Aaron", "Dale Murphy"))
    @patch("war_diamond_service.get_lineup", return_value=[
        {"position": "RF", "name": "Hank Aaron", "season": 1961, "value": 9.5, "display": "9.5 WAR", "team": "Atlanta Braves"},
        {"position": "SP", "name": "Greg Maddux", "season": 1995, "value": 9.7, "display": "9.7 WAR", "team": "Atlanta Braves"},
    ])
    def test_war_diamond_reveals_correct_position(self, _lineup, _names):
        response = app.test_client().post(
            "/mlb/war-diamond", data={"team": "ATL", "era": "modern", "player": "Hank Aaron"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Hank Aaron", response.data)
        self.assertIn(b"1961", response.data)
        self.assertIn(b"9.5 WAR", response.data)
        _lineup.assert_called_once_with("ATL", "medium", "single_season", "war")

    @patch("war_diamond_service.get_player_names", return_value=("Hank Aaron", "Dale Murphy"))
    @patch("war_diamond_service.get_lineup", return_value=[
        {"position": "RF", "name": "Hank Aaron", "season": 1961, "value": 9.5, "display": "9.5 WAR", "team": "Atlanta Braves"},
        {"position": "DH", "name": "Marcell Ozuna", "season": 2024, "value": 4.5, "display": "4.5 WAR", "team": "Atlanta Braves"},
    ])
    def test_war_diamond_has_era_choice_and_full_team_roster(self, _lineup, _names):
        response = app.test_client().get("/mlb/war-diamond?team=ATL&era=hard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="era-select"', response.data)
        self.assertIn(b'value="easy"', response.data)
        self.assertIn(b'value="medium"', response.data)
        self.assertIn(b'value="hard" selected', response.data)
        self.assertIn(b'value="single_season" checked', response.data)
        self.assertIn(b'value="career"', response.data)
        self.assertIn(b"Dale Murphy", response.data)
        self.assertIn(b"pos-dh", response.data)
        self.assertIn(b'id="diamond-stat-select"', response.data)
        self.assertIn(b"Home Runs", response.data)
        _lineup.assert_called_once_with("ATL", "hard", "single_season", "war")
        _names.assert_called_once_with("ATL", "hard", "war")

    @patch("war_diamond_service.get_player_names", return_value=("Andruw Jones",))
    @patch("war_diamond_service.get_lineup", return_value=[
        {"position": "CF", "name": "Andruw Jones", "season": None, "years": "1996–2007", "value": 61.0, "display": "61.0 WAR", "team": "Atlanta Braves"},
    ])
    def test_war_diamond_career_mode_displays_franchise_total(self, _lineup, _names):
        response = app.test_client().post("/mlb/war-diamond", data={
            "team": "ATL", "era": "hard", "war_mode": "career", "player": "Andruw Jones"
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("1996\u20132007 \u00b7 Career \u00b7 61.0 WAR".encode(), response.data)
        self.assertIn(b"Career with Franchise", response.data)
        _lineup.assert_called_once_with("ATL", "hard", "career", "war")

    @patch("war_diamond_service._appearances", return_value=pd.DataFrame([
        {"playerID": "olsonma02", "position": "1B"}, {"playerID": "aaronha01", "position": "RF"},
    ]))
    @patch("war_diamond_service._batting_records", return_value=pd.DataFrame([
        {"player_ID": "olsonma02", "name_common": "Matt Olson", "year_ID": 2023, "team_ID": "ATL", "HR": 54},
        {"player_ID": "aaronha01", "name_common": "Henry Aaron", "year_ID": 1954, "team_ID": "ML1", "HR": 398},
        {"player_ID": "aaronha01", "name_common": "Henry Aaron", "year_ID": 1973, "team_ID": "ATL", "HR": 40},
        {"player_ID": "aaronha01", "name_common": "Henry Aaron", "year_ID": 1974, "team_ID": "ATL", "HR": 295},
    ]))
    def test_fill_the_field_home_run_single_season_and_career_examples(self, _batting, _positions):
        from war_diamond_service import get_lineup
        get_lineup.cache_clear()
        season = {player["position"]: player for player in get_lineup("ATL", "hard", "single_season", "home_runs")}
        career = {player["position"]: player for player in get_lineup("ATL", "hard", "career", "home_runs")}
        self.assertEqual(season["1B"]["display"], "54 HR")
        self.assertEqual(season["1B"]["name"], "Matt Olson")
        self.assertEqual(career["RF"]["display"], "733 HR")
        self.assertEqual(career["RF"]["name"], "Hank Aaron")
        self.assertNotIn("P", season)
        self.assertNotIn("SP", season)
        self.assertNotIn("RP", season)
        get_lineup.cache_clear()

    def test_war_separates_starting_and_relief_pitchers(self):
        from war_diamond_service import STAT_OPTIONS, _pitching_lineup
        pitchers = pd.DataFrame([
            {"player_ID": "starter", "name_common": "Ace Starter", "year_ID": 2020, "WAR": 7.0, "G": 32, "GS": 32},
            {"player_ID": "reliever", "name_common": "Elite Closer", "year_ID": 2020, "WAR": 4.0, "G": 70, "GS": 0},
            {"player_ID": "swing", "name_common": "Swing Pitcher", "year_ID": 2020, "WAR": 5.0, "G": 40, "GS": 10},
        ])
        lineup = {player["position"]: player for player in _pitching_lineup(
            pitchers, "Test Team", "single_season", STAT_OPTIONS["war"]
        )}
        self.assertEqual(lineup["SP"]["name"], "Ace Starter")
        self.assertEqual(lineup["RP"]["name"], "Swing Pitcher")

    def test_relief_pitcher_is_positioned_left_of_catcher(self):
        with open("static/styles.css", encoding="utf-8") as styles_file:
            styles = styles_file.read()
        self.assertIn(".pos-sp{left:50%;top:64%}", styles)
        self.assertIn(".pos-rp{left:18%;top:88%}", styles)

    def test_war_diamond_difficulty_year_ranges_and_dh(self):
        from war_diamond_service import POSITION_COLUMNS, _in_era
        seasons = pd.DataFrame({"year_ID": [1900, 1901, 1949, 1950, 1969, 1970, 2025]})
        self.assertEqual(_in_era(seasons, "easy")["year_ID"].tolist(), [1970, 2025])
        self.assertEqual(_in_era(seasons, "medium")["year_ID"].tolist(), [1950, 1969, 1970, 2025])
        self.assertEqual(_in_era(seasons, "hard")["year_ID"].tolist(), [1901, 1949, 1950, 1969, 1970, 2025])
        self.assertEqual(POSITION_COLUMNS["DH"], "G_dh")

    def test_war_diamond_preserves_scroll_after_guess(self):
        with open("templates/war_diamond.html", encoding="utf-8") as template_file:
            template = template_file.read()
        self.assertIn("fill-field-scroll", template)
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
        self.assertIn(b"Quiz Your Friends", response.data)
        self.assertIn(b'name="min_year"', response.data)
        self.assertIn(b'name="max_year"', response.data)
        self.assertIn(b'name="groups"', response.data)
        self.assertIn(b'name="stats"', response.data)
        self.assertIn(b"data-stat-group", response.data)

    @patch("mlb_service.get_leaders", return_value=[{"name": "Player"}])
    def test_random_choice_redirects_to_leaderboard(self, _leaders):
        response = app.test_client().post("/mlb/random", data={
            "min_year": 2000, "max_year": 2025, "groups": "hitting", "stats": "hitting:avg"
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/mlb/leaderboard?", response.headers["Location"])
        self.assertIn("randomized=1", response.headers["Location"])
        self.assertIn("min_year=2000", response.headers["Location"])
        self.assertIn("groups=hitting", response.headers["Location"])

    @patch("nba_service.get_leaders", side_effect=[[], [{"name": "Available Player"}]])
    def test_random_choice_validates_and_respins_unavailable_data(self, leaders):
        response = app.test_client().post("/nba/random", data={
            "min_year": 1973, "max_year": 1975, "groups": "scoring", "stats": "scoring:FG_PCT"
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(leaders.call_count, 2)

    @patch("nba_service.get_leaders", side_effect=OSError("provider unavailable"))
    def test_unavailable_randomized_leaderboard_automatically_respins(self, _leaders):
        response = app.test_client().get(
            "/nba/leaderboard?season=1974&group=scoring&stat=FG_PCT&randomized=1&min_year=1973&max_year=1975&groups=scoring&stats=scoring:FG_PCT"
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/nba/random?", response.headers["Location"])
        self.assertIn("spin=1", response.headers["Location"])

    @patch("mlb_service.get_leaders", return_value=[{"name": "Rickey Henderson", "team": "OAK", "value": "65"}])
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

    def test_random_parameters_reject_stats_outside_selected_categories(self):
        response = app.test_client().post("/nba/random", data={
            "min_year": 2000, "max_year": 2025, "groups": "scoring", "stats": "defense:STL"
        })
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
        self.assertIn(b"Fill the Field", response.data)
        self.assertIn(b"Defensive Fill the Field", response.data)

    @patch("nfl_defense_service.get_player_names", return_value=("Chris Jones", "Trent McDuffie"))
    @patch("nfl_defense_service.get_lineup", return_value=[
        {"position": "DL1", "group": "DL", "name": "Chris Jones", "season": 2022, "years": None,
         "display": "15.5 SCK", "stat_label": "Sacks", "team": "Kansas City Chiefs"},
        {"position": "CB1", "group": "CB", "name": "Trent McDuffie", "season": 2024, "years": None,
         "display": "2 INT", "stat_label": "Interceptions", "team": "Kansas City Chiefs"},
    ])
    def test_nfl_defense_field_has_per_group_stats_and_reveals_guess(self, lineup, names):
        response = app.test_client().post("/nfl/fill-the-field/defense", data={
            "team": "KC", "timeframe": "single_season", "dl_stat": "sacks", "lb_stat": "tackles",
            "cb_stat": "interceptions", "s_stat": "interceptions", "player": "Chris Jones",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Chris Jones", response.data)
        self.assertIn(b"15.5 SCK", response.data)
        self.assertIn(b'id="dl-stat-select"', response.data)
        self.assertIn(b'id="lb-stat-select"', response.data)
        self.assertIn(b'id="cb-stat-select"', response.data)
        self.assertIn(b'id="s-stat-select"', response.data)
        lineup.assert_called_once_with("KC", "single_season", "sacks", "tackles", "interceptions", "interceptions")
        names.assert_called_once_with("KC")

    def test_nfl_defense_field_builds_eleven_position_slots(self):
        from nfl_defense_service import get_lineup
        rows = []
        positions = ["DE"] * 4 + ["LB"] * 3 + ["CB"] * 3 + ["S"] * 2
        for index, position in enumerate(positions, start=1):
            rows.append({"player_id": f"def{index}", "player_display_name": f"Defender {index}",
                         "position": position, "recent_team": "KC", "season": 2022,
                         "def_sacks": 20 - index, "tackles": 100 - index,
                         "def_interceptions": 15 - index, "def_tackles_for_loss": 25 - index,
                         "def_fumbles_forced": 20 - index})
        with patch("nfl_defense_service._defensive_data", return_value=pd.DataFrame(rows)), \
             patch("nfl_defense_service._historical_data", return_value=pd.DataFrame(columns=pd.DataFrame(rows).columns)):
            get_lineup.cache_clear()
            lineup = get_lineup("KC", "single_season", "sacks", "tackles", "interceptions", "forced_fumbles")
            self.assertEqual(len(lineup), 11)
            self.assertEqual({player["position"] for player in lineup},
                             {"DL1", "DL2", "DL3", "DL4", "LB1", "LB2", "LB3",
                              "CB1", "CB2", "S1", "S2"})
            get_lineup.cache_clear()

    def test_nfl_defense_career_combines_official_sacks_across_1999_boundary(self):
        from nfl_defense_service import get_lineup
        current = pd.DataFrame([{
            "player_id": "current-1", "player_display_name": "Boundary Defender", "position": "DE",
            "recent_team": "DET", "season": 1999, "def_sacks": 6, "tackles": 0,
            "def_interceptions": 0, "def_tackles_for_loss": 0, "def_fumbles_forced": 0,
        }])
        historical = pd.DataFrame([{
            "player_id": "archive-1", "player_display_name": "Boundary Defender", "position": "DE",
            "recent_team": "DET", "season": 1998, "def_sacks": 9, "tackles": 0,
            "def_interceptions": 0,
        }])
        with patch("nfl_defense_service._defensive_data", return_value=current), \
             patch("nfl_defense_service._historical_data", return_value=historical):
            get_lineup.cache_clear()
            lineup = get_lineup("DET", "career", "sacks", "tfl", "tfl", "tfl")
            self.assertEqual(lineup[0]["name"], "Boundary Defender")
            self.assertEqual(lineup[0]["display"], "15 SCK")
            self.assertEqual(lineup[0]["years"], "1998–1999")
            get_lineup.cache_clear()

    @patch("nfl_field_service.get_player_names", return_value=("Patrick Mahomes", "Jamaal Charles"))
    @patch("nfl_field_service.get_lineup", return_value=[
        {"position": "QB", "name": "Patrick Mahomes", "season": 2022, "years": None,
         "value": 5250, "display": "5,250 YDS", "team": "Kansas City Chiefs"},
        {"position": "RB", "name": "Jamaal Charles", "season": 2012, "years": None,
         "value": 1509, "display": "1,509 YDS", "team": "Kansas City Chiefs"},
    ])
    def test_nfl_fill_field_reveals_natural_position_stat(self, lineup, names):
        response = app.test_client().post("/nfl/fill-the-field", data={
            "team": "KC", "qb_stat": "passing_yards", "rb_stat": "rushing_yards",
            "wr_stat": "receiving_yards", "te_stat": "receiving_yards",
            "timeframe": "single_season", "player": "Patrick Mahomes"
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Patrick Mahomes", response.data)
        self.assertIn(b"5,250 YDS", response.data)
        self.assertIn(b"nfl-pos-qb", response.data)
        self.assertIn(b'id="qb-offense-stat-select"', response.data)
        self.assertIn(b'id="rb-offense-stat-select"', response.data)
        self.assertIn(b'id="wr-offense-stat-select"', response.data)
        self.assertIn(b'id="te-offense-stat-select"', response.data)
        lineup.assert_called_once_with("KC", "single_season", "passing_yards", "rushing_yards",
                                       "receiving_yards", "receiving_yards")
        names.assert_called_once_with("KC")

    @patch("nfl_service._weekly_data", return_value=pd.DataFrame([
        {"season": 2022, "season_type": "REG", "recent_team": "KC", "position": "QB", "player_id": "qb",
         "player_display_name": "Quarterback", "passing_yards": 5000, "passing_tds": 40},
        {"season": 2022, "season_type": "REG", "recent_team": "KC", "position": "RB", "player_id": "rb",
         "player_display_name": "Running Back", "rushing_yards": 1500, "rushing_tds": 15},
        {"season": 2022, "season_type": "REG", "recent_team": "KC", "position": "RB", "player_id": "rb2",
         "player_display_name": "Second Back", "rushing_yards": 900, "rushing_tds": 8},
        {"season": 2022, "season_type": "REG", "recent_team": "KC", "position": "WR", "player_id": "wr1",
         "player_display_name": "Wide One", "receiving_yards": 1400, "receiving_tds": 12},
        {"season": 2021, "season_type": "REG", "recent_team": "KC", "position": "WR", "player_id": "wr1",
         "player_display_name": "Wide One", "receiving_yards": 1300, "receiving_tds": 11},
        {"season": 2022, "season_type": "REG", "recent_team": "KC", "position": "WR", "player_id": "wr2",
         "player_display_name": "Wide Two", "receiving_yards": 1100, "receiving_tds": 9},
        {"season": 2022, "season_type": "REG", "recent_team": "KC", "position": "WR", "player_id": "wr3",
         "player_display_name": "Wide Three", "receiving_yards": 1000, "receiving_tds": 8},
        {"season": 2022, "season_type": "REG", "recent_team": "KC", "position": "TE", "player_id": "te",
         "player_display_name": "Tight End", "receiving_yards": 900, "receiving_tds": 10},
    ]))
    @patch("nfl_field_service._historical_data", return_value=pd.DataFrame(columns=[
        "player_id", "player_display_name", "field_position", "recent_team", "season",
        "passing_yards", "passing_tds", "rushing_yards", "rushing_tds", "receiving_yards", "receiving_tds",
    ]))
    @patch("nfl_field_service._latest_data", return_value=pd.DataFrame(columns=[
        "player_id", "player_display_name", "position", "recent_team", "season",
        "passing_yards", "passing_tds", "rushing_yards", "rushing_tds", "receiving_yards", "receiving_tds",
    ]))
    def test_nfl_fill_field_uses_natural_stats_for_seven_positions(self, _latest, _history, _data):
        from nfl_field_service import get_lineup
        get_lineup.cache_clear()
        yardage = {player["position"]: player for player in get_lineup("KC", "single_season")}
        touchdowns = {player["position"]: player for player in get_lineup(
            "KC", "single_season", "passing_tds", "rushing_tds", "receiving_tds", "receiving_tds"
        )}
        self.assertEqual(set(yardage), {"QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE"})
        self.assertEqual(yardage["QB"]["display"], "5,000 YDS")
        self.assertEqual(yardage["RB1"]["display"], "1,500 YDS")
        self.assertEqual(yardage["RB2"]["name"], "Second Back")
        self.assertEqual(yardage["WR1"]["display"], "1,400 YDS")
        self.assertEqual(yardage["WR2"]["name"], "Wide Two")
        self.assertEqual(yardage["WR3"]["name"], "Wide Three")
        self.assertEqual(touchdowns["QB"]["display"], "40 TD")
        self.assertEqual(touchdowns["TE"]["display"], "10 TD")
        get_lineup.cache_clear()

    def test_nfl_receiver_formation_is_balanced(self):
        with open("static/styles.css", encoding="utf-8") as styles_file:
            styles = styles_file.read()
        self.assertIn(".nfl-pos-wr1{left:13%;top:27%}.nfl-pos-wr2{left:87%;top:27%}", styles)
        self.assertIn(".nfl-pos-wr3{left:25%;top:47%}.nfl-pos-te{left:75%;top:47%}", styles)

    def test_nfl_offense_history_uses_regular_season_franchise_totals(self):
        from nfl_field_service import _historical_data
        history = _historical_data()
        barry = history.loc[
            (history["player_display_name"] == "Barry Sanders") & (history["recent_team"] == "DET"),
            "rushing_yards",
        ].sum()
        dawson = history.loc[
            (history["player_display_name"] == "Len Dawson") & (history["recent_team"] == "KC"),
            "passing_yards",
        ].sum()
        self.assertEqual(barry, 15269)
        self.assertEqual(dawson, 28507)

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
        self.assertIn(b"Fill the Court", response.data)

    def test_nba_fill_court_has_one_stat_control(self):
        response = app.test_client().get("/nba/fill-the-court?team=BOS&stat=ast")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Fill the Court", response.data)
        self.assertEqual(response.data.count(b'<select id="court-stat-select" name="stat">'), 1)
        for field in (b"pg_stat", b"sg_stat", b"sf_stat", b"pf_stat", b"c_stat"):
            self.assertNotIn(b'name="' + field + b'"', response.data)
        for position in (b"PG", b"SG", b"SF", b"PF", b"C"):
            self.assertIn(b">" + position + b"<", response.data)

    def test_nba_fill_court_uses_franchise_career_totals(self):
        from nba_court_service import get_lineup
        lineup = {player["position"]: player for player in get_lineup("LAL", "career", "pts")}
        self.assertEqual(lineup["SG"]["name"], "Kobe Bryant")
        self.assertEqual(lineup["SG"]["value"], 33643)

    @patch("nba_court_service.get_player_names", return_value=("Magic Johnson",))
    @patch("nba_court_service.get_lineup", return_value=tuple({
        "position": position, "name": "Magic Johnson" if position == "PG" else f"Player {position}",
        "season": None, "years": "1979–1990", "value": 10141 if position == "PG" else 100,
        "display": "10,141 AST" if position == "PG" else "100 PTS",
        "stat_label": "Assists" if position == "PG" else "Points", "team": "Los Angeles Lakers",
    } for position in ("PG", "SG", "SF", "PF", "C")))
    def test_nba_fill_court_reveals_guess(self, _lineup, _names):
        client = app.test_client()
        response = client.post("/nba/fill-the-court", data={
            "team": "LAL", "timeframe": "career", "stat": "ast", "player": "Magic Johnson",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Correct", response.data)
        self.assertIn(b"10,141 AST", response.data)

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
        self.assertIn(b"Fill the Field", response.data)

    def test_cfb_fill_field_has_program_and_group_controls(self):
        response = app.test_client().get(
            "/college-football/fill-the-field?team=Alabama&qb_stat=passing_yards&"
            "rb_stat=rushing_yards&wr_stat=receiving_yards&te_stat=receiving_yards"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Program Offense Challenge", response.data)
        self.assertIn(b"Alabama", response.data)
        for field in (b"qb_stat", b"rb_stat", b"wr_stat", b"te_stat"):
            self.assertIn(b'name="' + field + b'"', response.data)

    def test_cfb_fill_field_uses_official_box_totals(self):
        from cfb_field_service import get_lineup
        season = {player["position"]: player for player in get_lineup("Alabama")}
        career = {player["position"]: player for player in get_lineup("Alabama", "career")}
        self.assertEqual(season["RB1"]["name"], "Derrick Henry")
        self.assertEqual(season["RB1"]["value"], 2219)
        self.assertEqual(career["RB1"]["name"], "Najee Harris")
        self.assertEqual(career["RB1"]["value"], 3843)

    @patch("cfb_field_service.get_player_names", return_value=("Bryce Young",))
    @patch("cfb_field_service.get_lineup", return_value=tuple({
        "position": position, "group": position.rstrip("123"),
        "name": "Bryce Young" if position == "QB" else f"Player {position}",
        "season": 2021, "years": None, "value": 4872 if position == "QB" else 100,
        "display": "4,872 YDS" if position == "QB" else "100 YDS",
        "stat_label": "Passing Yards" if position == "QB" else "Yards", "team": "Alabama",
    } for position in ("QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE")))
    def test_cfb_fill_field_reveals_guess(self, _lineup, _names):
        response = app.test_client().post("/college-football/fill-the-field", data={
            "team": "Alabama", "timeframe": "single_season", "qb_stat": "passing_yards",
            "rb_stat": "rushing_yards", "wr_stat": "receiving_yards",
            "te_stat": "receiving_yards", "player": "Bryce Young",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Correct", response.data)
        self.assertIn(b"4,872 YDS", response.data)

    def test_cfb_defense_field_has_program_and_group_controls(self):
        response = app.test_client().get("/college-football/fill-the-field/defense?team=Alabama")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Program Defense Challenge", response.data)
        self.assertIn(b"Passes Defended", response.data)
        for field in (b"dl_stat", b"lb_stat", b"cb_stat", b"s_stat"):
            self.assertIn(b'name="' + field + b'"', response.data)

    def test_cfb_defense_field_builds_eleven_slots_for_every_fbs_program(self):
        from cfb_defense_service import TEAMS, get_lineup
        self.assertTrue(all(len(get_lineup(team)) == 11 for team in TEAMS))

    @patch("cfb_defense_service.get_player_names", return_value=("Defender One",))
    @patch("cfb_defense_service.get_lineup", return_value=tuple({
        "position": position, "group": position.rstrip("1234"), "name": "Defender One",
        "season": 2024, "years": None, "display": "10 SCK", "stat_label": "Sacks",
        "team": "Alabama",
    } for position in ("DL1", "DL2", "DL3", "DL4", "LB1", "LB2", "LB3", "CB1", "CB2", "S1", "S2")))
    def test_cfb_defense_field_reveals_guess(self, _lineup, _names):
        response = app.test_client().post("/college-football/fill-the-field/defense", data={
            "team": "Alabama", "timeframe": "single_season", "dl_stat": "sacks",
            "lb_stat": "tackles", "cb_stat": "interceptions", "s_stat": "interceptions",
            "player": "Defender One",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Correct", response.data)
        self.assertIn(b"10 SCK", response.data)

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
