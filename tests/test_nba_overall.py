import unittest
import nba_overall_service as overall
import nba_overall_benchmark as benchmark

def profile(**ratings):
    return {"attributes": tuple({"id": key, "rating": value} for key, value in ratings.items())}

def detailed(summary, **granular):
    value=profile(**summary);value["granular_attributes"]=tuple({"id":k,"rating":v} for k,v in granular.items());return value

class NBAOverallTests(unittest.TestCase):
    def test_external_benchmark_sets_elite_anchors_and_corrects_role_player(self):
        self.assertEqual(benchmark.calibrated_overall("Nikola Jokic", 79), 99)
        self.assertEqual(benchmark.calibrated_overall("Shai Gilgeous-Alexander", 83), 99)
        self.assertEqual(benchmark.calibrated_overall("Payton Pritchard", 84), 80)

    def test_external_benchmark_falls_back_for_unknown_player(self):
        self.assertEqual(benchmark.calibrated_overall("Unmatched Test Player", 77), 77)

    def test_guard_core_skills_outweigh_big_man_skills(self):
        elite=profile(scoring=92,playmaking=94,finishing=84,rebounding=45,steal_hands=70,rim_protection=30)
        wrong=profile(scoring=58,playmaking=48,finishing=70,rebounding=94,steal_hands=76,rim_protection=88)
        self.assertGreater(overall.calculate(elite,"G"),overall.calculate(wrong,"G")+10)
    def test_rebounding_is_bonus_for_guard_but_core_for_center(self):
        low=profile(scoring=75,playmaking=75,finishing=75,rebounding=40,steal_hands=70,rim_protection=65)
        high=profile(scoring=75,playmaking=75,finishing=75,rebounding=90,steal_hands=70,rim_protection=65)
        self.assertLess(overall.calculate(high,"G")-overall.calculate(low,"G"),5)
        self.assertGreater(overall.calculate(high,"C")-overall.calculate(low,"C"),5)
    def test_missing_attribute_is_not_zero(self):
        missing=profile(scoring=80,playmaking=80,finishing=80,rebounding=70,steal_hands=70)
        zero=profile(scoring=80,playmaking=80,finishing=80,rebounding=70,steal_hands=70,rim_protection=25)
        self.assertGreater(overall.calculate(missing,"C"),overall.calculate(zero,"C"))
    def test_debug_is_versioned_and_explainable(self):
        report=overall.calculate(profile(scoring=80,playmaking=80,finishing=80,rebounding=70,steal_hands=70,rim_protection=60),"G",True)
        self.assertEqual(report["model_version"],"v2-positional-value")
        self.assertIn("core_penalty",report)
    def test_hybrid_blends_instead_of_selecting_best_position(self):
        sample=profile(scoring=82,playmaking=78,finishing=84,rebounding=80,steal_hands=74,rim_protection=72)
        hybrid=overall.calculate(sample,"G/F")
        guard,forward=overall.calculate(sample,"G"),overall.calculate(sample,"F")
        self.assertGreaterEqual(hybrid,min(guard,forward));self.assertLessEqual(hybrid,max(guard,forward))
    def test_core_skill_curve_is_smooth_and_monotonic(self):
        values=[]
        for playmaking in (25,35,45,55,65,75,85,95):
            values.append(overall.calculate(profile(scoring=75,playmaking=playmaking,finishing=75,rebounding=60,steal_hands=70,rim_protection=45),"G"))
        self.assertEqual(values,sorted(values))
        self.assertLessEqual(max(b-a for a,b in zip(values,values[1:])),10)
    def test_proxy_evidence_is_lower_confidence_than_direct(self):
        self.assertLess(overall.EVIDENCE_QUALITY["PROXY"], overall.EVIDENCE_QUALITY["DIRECT_HIGH"])
        self.assertEqual(overall.GROUP_EVIDENCE["screening"], "FALLBACK")
    def test_creation_uses_self_creation_and_volume_not_generic_efficiency(self):
        creator=detailed({"scoring":80,"playmaking":75,"finishing":75},self_created_scoring=90,scoring_volume=90,overall_shooting=75,three_point_shooting=75,free_throw_shooting=75)
        specialist=detailed({"scoring":90,"playmaking":75,"finishing":75},self_created_scoring=45,scoring_volume=60,overall_shooting=95,three_point_shooting=95,free_throw_shooting=90)
        self.assertGreater(overall.calculate(creator,"PG"),overall.calculate(specialist,"PG"))
    def test_post_offense_requires_post_action_evidence(self):
        sample=detailed({"scoring":90,"playmaking":70,"finishing":95,"rebounding":85,"rim_protection":80,"steal_hands":60},scoring_volume=90,self_created_scoring=80)
        self.assertNotIn("post_offense",overall.calculate(sample,"C",True)["groups"])

if __name__ == "__main__": unittest.main()
