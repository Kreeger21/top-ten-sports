import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

import nba_official_features as official
from scripts import build_nba_official_features as builder


class NBAOfficialFeatureTests(unittest.TestCase):
    def tearDown(self):
        official.clear_cache()

    def test_result_set_normalization(self):
        payload = {"resultSets": [{"headers": ["PLAYER_ID", "PLAYER_NAME", "AST_PCT"],
                                    "rowSet": [[1, "Player One", .31]]}]}
        self.assertEqual(builder._result_rows(payload)[0]["AST_PCT"], .31)

    def test_missing_cache_is_safe(self):
        with patch.object(official, "DATA_PATH", Path("missing-official-cache.json")):
            official.clear_cache()
            self.assertEqual(official.snapshot()["status"], "not_loaded")
            self.assertEqual(official.features_for_player("anyone"), {})

    def test_invalid_cache_is_safe(self):
        path = Path("invalid-cache.json")
        with patch.object(official, "DATA_PATH", path), patch.object(Path, "exists", return_value=True), \
                patch.object(Path, "open", mock_open(read_data="not-json")):
                official.clear_cache()
                self.assertEqual(official.snapshot()["status"], "invalid")

    def test_valid_cache_returns_player_features(self):
        payload = '{"status":"verified","players":{"abc":{"player":"A"}},"sources":[]}'
        path = Path("valid-cache.json")
        with patch.object(official, "DATA_PATH", path), patch.object(Path, "exists", return_value=True), \
                patch.object(Path, "open", mock_open(read_data=payload)):
                official.clear_cache()
                self.assertEqual(official.features_for_player("abc")["player"], "A")


if __name__ == "__main__":
    unittest.main()
