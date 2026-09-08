import unittest

import nba_attribute_service as attributes
import nba_franchise_service as franchise


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
        self.assertNotIn("three_point_volume", attribute_ids)
        self.assertIn("three_point_volume", tendency_ids)
        self.assertNotIn("overall", attribute_ids)

    def test_missing_player_mapping_does_not_create_ratings(self):
        self.assertIsNone(attributes.attributes_for_player("not-a-player"))

    def test_roster_screen_displays_attributes_and_unrated_state(self):
        from app import app
        response = app.test_client().get("/franchise/nba/roster?team=ATL")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Player attributes", response.data)
        self.assertIn(b"Scoring", response.data)
        self.assertIn(b"Not rated", response.data)


if __name__ == "__main__":
    unittest.main()
