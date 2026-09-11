import unittest

import nba_possession_service as service


def possession(**changes):
    base=dict(game_id="g1",season=2025,possession_id="g1:1:1",period=1,start_time=700,end_time=694,
              duration=6,offensive_team="A",defensive_team="B",offensive_players=["p1","p2","p5","p6","p7"],
              defensive_players=["p3","p4","p8","p9","p10"],possession_start_type="Steal",events=[],points=0,
              provenance={"source":"pbpstats","underlying_data_source":"stats.nba.com"})
    base.update(changes);return service.CanonicalPossession(**base)


class PossessionTests(unittest.TestCase):
    def test_start_classification_prefers_structured_steal(self):
        self.assertEqual(service.classify_start({"turnover_player":"p1","steal_player":"p2"}),"Steal")

    def test_end_classification_uses_event_sequence(self):
        events=[{"shot_attempt":True,"made":False},{"defensive_rebound":"p3"}]
        self.assertEqual(service.classify_end(events),"Missed FG + defensive rebound")

    def test_transition_requires_multiple_signals(self):
        label,confidence=service.classify_transition("Steal",6,[{"shot_attempt":True}])
        self.assertEqual(label,"Likely Transition");self.assertGreaterEqual(confidence,.4)
        label,confidence=service.classify_transition("Steal",6,[{"shot_attempt":True,"fast_break":True}])
        self.assertEqual(label,"High Confidence Transition");self.assertGreaterEqual(confidence,.8)

    def test_ambiguous_transition_remains_unknown(self):
        self.assertEqual(service.classify_transition("Other",None,[])[0],"Unknown")

    def test_post_classifier_is_central_and_action_specific(self):
        self.assertEqual(service.classify_post_action("Jokic turnaround fadeaway shot"),"turnaround_fadeaway")
        self.assertIsNone(service.classify_post_action("corner three pointer"))

    def test_second_chance_stays_with_same_possession(self):
        p=possession(events=[{"shot_attempt":True,"made":False},{"offensive_rebound":"p2"},
                             {"shot_attempt":True,"shot_player":"p2","made":True,"points":2}])
        self.assertEqual(len(service.second_chance_actions(p)),1)

    def test_player_aggregation_preserves_counts_before_rates(self):
        p=possession(shot_attempt=True,shot_player="p1",shot_result="made",assist_player=None,points=2,
                     transition_class="High Confidence Transition",transition_confidence=.9)
        result=service.aggregate_player_possessions([p])["p1"]
        self.assertEqual(result["counts"]["offensive_possessions"],1)
        self.assertEqual(result["features"]["unassisted_make_rate"],1)
        self.assertEqual(result["provenance"]["source"],"pbpstats")

    def test_multiseason_aggregation_weights_numerators_and_denominators(self):
        first=possession(season=2025,shot_attempt=True,shot_player="p1",shot_result="made",points=2)
        old=possession(season=2024,possession_id="old",shot_attempt=True,shot_player="p1",shot_result="missed",points=0)
        result=service.aggregate_player_possessions([first,old])["p1"]["counts"]
        self.assertAlmostEqual(result["offensive_possessions"],1.65)
        self.assertAlmostEqual(result["fga"],1.65)

    def test_lineup_possessions_support_on_off_context(self):
        on=possession(offensive_players=["p1","p2","p5","p6","p7"],defensive_players=["p3","p4","p8","p9","p10"],points=2)
        off=possession(possession_id="g1:1:2",offensive_players=["p11","p2","p5","p6","p7"],
                       defensive_players=["p3","p4","p8","p9","p10"],points=0)
        result=service.aggregate_player_possessions([on,off])["p1"]
        self.assertEqual(result["counts"]["offensive_possessions"],1)
        self.assertEqual(result["features"]["on_court_ortg"],200)
        self.assertEqual(result["features"]["off_court_ortg"],0)

    def test_role_context_uses_league_burden_distribution(self):
        possessions=[]
        for index, shooter in enumerate(("p1","p1","p2","p3")):
            possessions.append(possession(possession_id=f"g1:1:{index}",offensive_players=["p1","p2","p3","p5","p6"],
                                           defensive_players=["p7","p8","p9","p10","p11"],shot_player=shooter,shot_attempt=True))
        result=service.aggregate_player_possessions(possessions)
        self.assertIn(result["p1"]["features"]["role_context"],{"Primary Creator","Secondary Creator"})

    def test_missing_lineup_data_does_not_invent_on_court_possessions(self):
        p=possession(offensive_players=[],defensive_players=[],shot_attempt=True,shot_player="p1",shot_result="made")
        result=service.aggregate_player_possessions([p])["p1"]
        self.assertNotIn("offensive_possessions",result["counts"])
        self.assertIsNone(result["features"]["creation_burden"])

    def test_possession_provenance_has_required_lineage(self):
        provenance=service.Provenance("pbpstats","stats.nba.com",2025,"g1","adapter")
        self.assertEqual(provenance.model_version,service.MODEL_VERSION)
        self.assertEqual(provenance.evidence_tier,"Direct Open-Data Possession Evidence")


if __name__=="__main__": unittest.main()
