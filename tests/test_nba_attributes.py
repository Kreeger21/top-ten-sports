import unittest

import nba_attribute_service as attributes
import nba_franchise_service as franchise
from nba_court_zones import classify_shot


class NBAAttributeTests(unittest.TestCase):
    def test_ratings_are_versioned_bounded_and_explainable(self):
        profiles = [player["attribute_profile"] for team in franchise.TEAMS
                    for player in franchise.roster(team.code) if player["attribute_profile"]]
        self.assertTrue(profiles)
        for profile in profiles:
            self.assertEqual(profile["model_version"], attributes.MODEL_VERSION)
            for rating in profile["attributes"]:
                self.assertGreaterEqual(rating["rating"], attributes.RATING_MIN)
                self.assertLessEqual(rating["rating"], attributes.RATING_MAX)
                self.assertIn("confidence", rating)
                self.assertIn("description", rating)

    def test_tendencies_are_separate_from_skill_attributes(self):
        profile = next(player["attribute_profile"] for player in franchise.roster("ATL")
                       if player["attribute_profile"])
        attribute_ids = {item["id"] for item in profile["attributes"]}
        tendency_ids = {item["id"] for item in profile["tendencies"]}
        self.assertNotIn("three_point_attempt", attribute_ids)
        self.assertIn("three_point_attempt", tendency_ids)
        self.assertNotIn("overall", attribute_ids)

    def test_summary_ratings_are_derived_from_granular_children(self):
        profile = next(player["attribute_profile"] for player in franchise.roster("ATL")
                       if player["attribute_profile"])
        granular = {item["id"]: item for item in profile["granular_attributes"]}
        for summary in profile["attributes"]:
            self.assertTrue(summary["children"])
            self.assertTrue(all(child in granular for child in summary["children"]))
            self.assertGreaterEqual(summary["rating"], min(granular[child]["rating"] for child in summary["children"]))
            self.assertLessEqual(summary["rating"], max(granular[child]["rating"] for child in summary["children"]))

    def test_event_categories_are_available_while_unloaded_tracking_stays_unrated(self):
        profile = next(player["attribute_profile"] for player in franchise.roster("ATL")
                       if player["attribute_profile"])
        finishing = next(category for category in profile["categories"] if category["name"] == "Finishing")
        handling = next(category for category in profile["categories"] if category["name"] == "Ball Handling")
        self.assertEqual(finishing["status"], "available")
        self.assertGreater(len(finishing["attributes"]), 0)
        self.assertEqual(handling["status"], "not-tracked")
        self.assertEqual(handling["attributes"], ())

    def test_final_rating_uses_league_percentile_not_position_percentile(self):
        definition = next(item for item in attributes.ATTRIBUTE_DEFINITIONS if item.id == "total_rebounding")
        population = tuple(attributes._player_features().values())
        guard = attributes._player_features()["balllo01"]
        result = attributes._calculate(guard, definition, population)
        self.assertGreater(result["position_percentile"], result["league_percentile"])
        self.assertEqual(result["reference_population"], "NBA-wide")
        self.assertLess(result["rating"], 70)

    def test_low_volume_three_point_sample_is_shrunk(self):
        definition = next(item for item in attributes.ATTRIBUTE_DEFINITIONS if item.id == "three_point_shooting")
        keys = ("g", "gs", "mp", "fg", "fga", "x3p", "x3pa", "x2p", "x2pa", "ft", "fta", "orb", "drb", "trb", "ast", "stl", "blk", "tov", "pf", "pts")
        base = {key: 0.0 for key in keys}
        low_sample = {**base, "position": "G", "mp": 100, "fga": 20, "x3p": 4, "x3pa": 8}
        population = tuple(attributes._player_features().values()) + (low_sample,)
        result = attributes._calculate(low_sample, definition, population)
        self.assertLess(result["rating"], 80)
        self.assertLess(result["reliability"], 5)

    def test_court_zone_classification(self):
        self.assertEqual(classify_shot(-23, 5), "left-corner-three")
        self.assertEqual(classify_shot(23, 5), "right-corner-three")
        self.assertEqual(classify_shot(0, 24), "above-break-three-center")

    def test_missing_player_mapping_does_not_create_ratings(self):
        self.assertIsNone(attributes.attributes_for_player("not-a-player"))

    def test_roster_screen_displays_attributes_and_unrated_state(self):
        from app import app
        response = app.test_client().get("/franchise/nba/roster?team=ATL")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Player attributes", response.data)
        self.assertIn(b"Scoring", response.data)
        self.assertIn(b"Not rated", response.data)

    def test_player_attributes_page_is_linked_and_explains_missing_data(self):
        from app import app
        player = next(player for player in franchise.roster("ATL") if player["attribute_profile"])
        client = app.test_client()
        roster = client.get("/franchise/nba/roster?team=ATL")
        self.assertIn(f"/franchise/nba/players/{player['player_id']}/attributes".encode(), roster.data)
        response = client.get(f"/franchise/nba/players/{player['player_id']}/attributes?team=ATL")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Summary ratings", response.data)
        self.assertIn(b"Not tracked", response.data)
        self.assertIn(b"Tendencies", response.data)


if __name__ == "__main__":
    unittest.main()
