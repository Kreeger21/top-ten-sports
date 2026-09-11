import unittest

from scripts import nba_2k_calibration as calibration


class NBA2KCalibrationTests(unittest.TestCase):
    def test_broad_positions_follow_primary_listing(self):
        self.assertEqual(calibration.broad_position("PG / SG"),"G")
        self.assertEqual(calibration.broad_position("PF / C"),"F")
        self.assertEqual(calibration.broad_position("C"),"C")

    def test_snapshot_has_full_current_roster_and_attributes(self):
        rows=calibration.load()
        self.assertGreaterEqual(len(rows),500)
        self.assertTrue(all(len(row["values"])==6 for row in rows))

    def test_positional_benchmark_is_predictive_but_diagnostic(self):
        rows=calibration.load()
        for position in ("G","F","C"):
            model=calibration.ridge_fit([row for row in rows if row["position"]==position])
            self.assertGreater(model["test_r2"],.75)
            self.assertLess(model["test_mae"],3)


if __name__=="__main__":unittest.main()
