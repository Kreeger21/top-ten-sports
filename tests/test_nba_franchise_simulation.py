import unittest
from pathlib import Path
from unittest.mock import patch

from app import app
import nba_franchise_service as franchise
import nba_franchise_simulation as simulation


class NBAFranchiseSimulationTests(unittest.TestCase):
    save_dir = Path(__file__).parent / "fixtures" / "nba_franchise_saves"

    def setUp(self):
        for path in self.save_dir.glob("*.json"):
            path.unlink()

    def tearDown(self):
        for path in self.save_dir.glob("*.json"):
            path.unlink()

    def test_every_team_has_a_roster_based_strength(self):
        self.assertEqual(franchise.TEAMS[0].code, "ATL")
        self.assertEqual([team.city for team in franchise.TEAMS], sorted(team.city for team in franchise.TEAMS))
        strengths = [simulation.team_strength(team.code) for team in franchise.TEAMS]
        self.assertTrue(all(25 <= item["overall"] <= 99 for item in strengths))
        self.assertGreater(len({item["overall"] for item in strengths}), 5)

    def test_player_and_team_rankings_are_complete_and_sorted(self):
        players = simulation.player_rankings(limit=100)
        teams = simulation.team_rankings()
        self.assertEqual(len(players), 100)
        self.assertEqual(len(teams), 30)
        self.assertEqual([row["overall"] for row in players],
                         sorted((row["overall"] for row in players), reverse=True))
        self.assertEqual([row["overall"] for row in teams],
                         sorted((row["overall"] for row in teams), reverse=True))
        match = simulation.player_rankings("Jalen Brunson", 100)
        self.assertTrue(match)
        self.assertTrue(all("jalen brunson" in row["name"].casefold() for row in match))

    def test_results_follow_schedule_and_persist(self):
        with patch.object(simulation, "SAVE_DIR", self.save_dir):
            save = simulation.create("NYK")
            simulation.simulate(save, 4)
            loaded = simulation.load(save["id"])
            expected = franchise.regular_season_schedule("NYK")[:4]
            self.assertEqual([result["game"] for result in loaded["results"]], [1, 2, 3, 4])
            self.assertEqual([result["opponent"] for result in loaded["results"]],
                             [game["opponent"] for game in expected])
            self.assertTrue(all(result["team_score"] != result["opponent_score"]
                                for result in loaded["results"]))
            self.assertTrue(all(result["engine"] == "roster-attributes-v2"
                                for result in loaded["results"]))
            for result in loaded["results"]:
                self.assertEqual(sum(row["pts"] for row in result["box_score"]["NYK"]),
                                 result["team_score"])
                self.assertEqual(sum(row["pts"] for row in result["box_score"][result["opponent"]]),
                                 result["opponent_score"])

    def test_simulated_stats_and_two_team_box_score_render(self):
        with patch.object(simulation, "SAVE_DIR", self.save_dir):
            client = app.test_client()
            client.post("/franchise/nba/start", data={"team": "OKC"})
            dashboard = client.post("/franchise/nba/simulate", data={"advance": "game"},
                                    follow_redirects=True)
            self.assertIn(b"Simulated player stats", dashboard.data)
            self.assertIn(b">Schedule</h2>", dashboard.data)
            self.assertIn(b"Latest box score", dashboard.data)
            stats = client.get("/franchise/nba/simulated-stats?team=OKC")
            self.assertIn(b"Player performance", stats.data)
            self.assertIn(b"FG%", stats.data)
            box = client.get("/franchise/nba/games/1?team=OKC")
            self.assertIn(b"Your team", box.data)
            self.assertIn(b"Opponent", box.data)
            self.assertEqual(box.data.count(b'<table class="sim-stats-table">'), 2)

    def test_simulation_stops_after_single_82_game_season(self):
        with patch.object(simulation, "SAVE_DIR", self.save_dir):
            save = simulation.create("BOS")
            for _ in range(21):
                simulation.simulate(save, 4)
            state = simulation.season_state(save)
            self.assertEqual(state["games_played"], 82)
            self.assertEqual(state["games_remaining"], 0)
            self.assertTrue(state["season_complete"])
            self.assertIsNone(state["next_game"])

    def test_started_franchise_locks_team_and_autosaves(self):
        with patch.object(simulation, "SAVE_DIR", self.save_dir):
            client = app.test_client()
            setup = client.get("/franchise/nba")
            self.assertIn(b"Choose your franchise", setup.data)
            started = client.post("/franchise/nba/start", data={"team": "NYK"}, follow_redirects=True)
            self.assertIn(b"New York Knicks", started.data)
            self.assertIn(b"Selection locked", started.data)
            self.assertNotIn(b'id="team-select"', started.data)

            locked = client.get("/franchise/nba?team=BOS")
            self.assertIn(b"New York Knicks", locked.data)
            self.assertNotIn(b"Boston Celtics", locked.data)
            simulated = client.post("/franchise/nba/simulate", data={"advance": "game"},
                                    follow_redirects=True)
            self.assertIn(b"1 of 82 games played", simulated.data)
            self.assertIn(b"Progress saves automatically", simulated.data)

    def test_end_franchise_requires_confirmation_and_deletes_save(self):
        with patch.object(simulation, "SAVE_DIR", self.save_dir):
            client = app.test_client()
            client.post("/franchise/nba/start", data={"team": "ATL"})
            with client.session_transaction() as browser_session:
                save_id = browser_session["nba_franchise_save_id"]
            confirmation = client.get("/franchise/nba/end")
            self.assertIn(b"End this franchise?", confirmation.data)
            self.assertTrue((self.save_dir / f"{save_id}.json").exists())

            ended = client.post("/franchise/nba/end", follow_redirects=True)
            self.assertIn(b"Choose your franchise", ended.data)
            self.assertFalse((self.save_dir / f"{save_id}.json").exists())
            with client.session_transaction() as browser_session:
                self.assertNotIn("nba_franchise_save_id", browser_session)

    def test_setup_previews_and_full_ranking_pages_render(self):
        client = app.test_client()
        setup = client.get("/franchise/nba")
        self.assertIn(b"Top 10 players", setup.data)
        self.assertIn(b"Top 10 teams", setup.data)
        players = client.get("/franchise/nba/rankings/players?q=Brunson")
        teams = client.get("/franchise/nba/rankings/teams")
        self.assertIn(b"Top 100 players", players.data)
        self.assertIn(b"Jalen Brunson", players.data)
        self.assertIn(b"Search players", players.data)
        self.assertIn(b"All 30 teams", teams.data)
        self.assertEqual(teams.data.count(b"--rank-primary:"), 30)

    def test_user_can_leave_resume_and_keep_multiple_franchises(self):
        with patch.object(simulation, "SAVE_DIR", self.save_dir):
            client = app.test_client()
            client.post("/franchise/nba/start", data={"team": "ATL"})
            with client.session_transaction() as browser_session:
                atl_id = browser_session["nba_franchise_save_id"]
            client.post("/franchise/nba/simulate", data={"advance": "game"})
            library = client.post("/franchise/nba/leave", follow_redirects=True)
            self.assertIn(b"Previously started franchises", library.data)
            self.assertIn(b"Atlanta Hawks", library.data)
            self.assertIn(b"1 of 82 games played", library.data)

            client.post("/franchise/nba/start", data={"team": "BOS"})
            with client.session_transaction() as browser_session:
                bos_id = browser_session["nba_franchise_save_id"]
                self.assertEqual(set(browser_session["nba_franchise_save_ids"]), {atl_id, bos_id})
            client.post("/franchise/nba/leave")
            library = client.get("/franchise/nba")
            self.assertIn(b"Atlanta Hawks", library.data)
            self.assertIn(b"Boston Celtics", library.data)

            resumed = client.post(f"/franchise/nba/load/{atl_id}", follow_redirects=True)
            self.assertIn(b"ATLANTA HAWKS", resumed.data.upper())
            self.assertIn(b"1 of 82 games played", resumed.data)
            self.assertTrue((self.save_dir / f"{bos_id}.json").exists())

    def test_trade_center_accepts_balanced_assets_and_updates_rosters(self):
        with patch.object(simulation, "SAVE_DIR", self.save_dir):
            client = app.test_client()
            client.post("/franchise/nba/start", data={"team": "ATL"})
            with client.session_transaction() as browser_session:
                save = simulation.load(browser_session["nba_franchise_save_id"])
            atl = sorted(simulation.roster_for_save(save, "ATL"), key=simulation._player_quality)
            bos = sorted(simulation.roster_for_save(save, "BOS"), key=simulation._player_quality)
            outgoing = min(atl, key=lambda player: abs(simulation._asset_value(player) - simulation._asset_value(bos[len(bos)//2])))
            incoming = min(bos, key=lambda player: abs(simulation._asset_value(player) - simulation._asset_value(outgoing)))
            response = client.post("/franchise/nba/trades", data={"partner": "BOS",
                "user_player": outgoing["player_id"], "cpu_player": incoming["player_id"]},
                follow_redirects=True)
            self.assertIn(b"Trade accepted", response.data)
            save = simulation.load(save["id"])
            self.assertIn(incoming["player_id"], {player["player_id"] for player in simulation.roster_for_save(save, "ATL")})
            self.assertTrue(save["transactions"])

    def test_cpu_trade_is_logged_during_season(self):
        with patch.object(simulation, "SAVE_DIR", self.save_dir):
            save = simulation.create("NYK")
            simulation.simulate(save, 7)
            simulation.simulate(save, 2)
            loaded = simulation.load(save["id"])
            self.assertTrue(any(item["type"] == "League trade" for item in loaded["transactions"]))

    def test_declined_trade_preserves_all_offer_slots(self):
        with patch.object(simulation, "SAVE_DIR", self.save_dir):
            client = app.test_client()
            client.post("/franchise/nba/start", data={"team": "ATL"})
            with client.session_transaction() as browser_session:
                save = simulation.load(browser_session["nba_franchise_save_id"])
            outgoing = min((player for player in simulation.roster_for_save(save, "ATL")
                            if player["contract_verified"]), key=simulation._player_quality)
            incoming = max(simulation.roster_for_save(save, "OKC"), key=simulation._player_quality)
            page = client.post("/franchise/nba/trades", data={"partner": "OKC",
                "user_player": [outgoing["player_id"], "", ""],
                "cpu_player": [incoming["player_id"], "", ""]}, follow_redirects=True)
            self.assertIn(b"The CPU declined", page.data)
            self.assertIn(f'value="{outgoing["player_id"]}" selected'.encode(), page.data)
            self.assertIn(f'value="{incoming["player_id"]}" selected'.encode(), page.data)
            self.assertEqual(page.data.count(b'name="user_player"'), 1)
            self.assertEqual(page.data.count(b'name="cpu_pick"'), 1)
            self.assertIn(b"Add player", page.data)
            self.assertIn(b"Remove pick", page.data)


if __name__ == "__main__":
    unittest.main()
