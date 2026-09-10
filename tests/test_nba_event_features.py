import unittest

import pandas as pd

from scripts import build_nba_event_features as builder


class NBAEventFeatureTests(unittest.TestCase):
    def test_normalizes_hoopr_full_court_coordinates(self):
        self.assertEqual(builder.normalize_coordinates(-41.75, 2), (2.0, 0.0))
        self.assertEqual(builder.normalize_coordinates(30.75, -3), (-3.0, 11.0))

    def test_aggregate_validates_and_derives_real_events(self):
        frame = pd.DataFrame([
            {"shooting_play": True, "season_type": 2, "athlete_id_1": 1, "athlete_name_1": "Test Player",
             "coordinate_x": 39.75, "coordinate_y": 1, "scoring_play": True, "score_value": 2,
             "type_text": "Driving Layup Shot", "text": "Test Player makes layup (Helper assists)"},
            {"shooting_play": True, "season_type": 2, "athlete_id_1": 1, "athlete_name_1": "Test Player",
             "coordinate_x": -18, "coordinate_y": 24, "scoring_play": False, "score_value": 0,
             "type_text": "Jump Shot", "text": "Test Player misses three point jumper"},
        ])
        players = {}
        report = builder.aggregate_frame(frame, 2025, {"test player": "test01"}, players)
        result = builder._finalize(players["test01"])
        self.assertEqual(report["accepted_shots"], 2)
        self.assertEqual(result["features"]["rim_pct"], 1)
        self.assertEqual(result["features"]["layup_pct"], 1)
        self.assertEqual(result["features"]["unassisted_make_rate"], 0)

    def test_missing_required_columns_fail_validation(self):
        with self.assertRaises(ValueError):
            builder.aggregate_frame(pd.DataFrame([{"shooting_play": True}]), 2025, {}, {})


if __name__ == "__main__":
    unittest.main()
