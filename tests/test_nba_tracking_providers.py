import unittest
from unittest.mock import patch

import requests

import nba_tracking_providers as providers


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))
    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class ProviderTests(unittest.TestCase):
    def test_missing_credential_fails_gracefully(self):
        provider = providers.SportradarNBAProvider(providers.ProviderConfig())
        with self.assertRaisesRegex(providers.ProviderUnavailable, "credential"):
            provider.game_summary("game")

    def test_trial_and_production_configuration(self):
        self.assertEqual(providers.ProviderConfig(access_level="trial").access_level, "trial")
        self.assertEqual(providers.ProviderConfig(access_level="production").access_level, "production")
        with self.assertRaises(ValueError):
            providers.ProviderConfig(access_level="private")

    def test_environment_configuration_and_no_secret_in_provenance(self):
        with patch.dict("os.environ", {"SPORTRADAR_API_KEY": "secret", "SPORTRADAR_ACCESS_LEVEL": "trial"}, clear=True):
            config = providers.ProviderConfig.from_env()
        self.assertEqual(config.api_key, "secret")
        feature = providers.HoopRFallbackProvider.rim_attack_proxy("1", 2025, 10, 20)
        self.assertNotIn("secret", str(feature.as_dict()))

    def test_http_error_and_schema_change(self):
        config = providers.ProviderConfig(api_key="test")
        provider = providers.SportradarNBAProvider(config, FakeSession([FakeResponse({}, 500)]))
        with self.assertRaises(providers.ProviderUnavailable):
            provider.game_summary("g")
        provider = providers.SportradarNBAProvider(config, FakeSession([FakeResponse([])]))
        with self.assertRaises(providers.ProviderSchemaError):
            provider.game_summary("g")

    def test_access_level_is_used_and_key_only_in_header(self):
        session = FakeSession([FakeResponse({"game": {}})])
        provider = providers.SportradarNBAProvider(
            providers.ProviderConfig(api_key="test", access_level="production"), session)
        provider.game_play_by_play("abc")
        url, call = session.calls[0]
        self.assertIn("/production/v8/en/games/abc/pbp.json", url)
        self.assertNotIn("test", url)
        self.assertEqual(call["headers"], {"x-api-key": "test"})

    def test_synergy_pagination_and_duplicate_rows(self):
        first = [{"id": "1"}, {"id": "2"}]
        second = [{"id": "2"}]
        session = FakeSession([FakeResponse({"data": first}), FakeResponse({"data": second})])
        provider = providers.SportradarSynergyProvider(
            providers.ProviderConfig(api_key="test"), session)
        rows = provider.player_report("g", "t", page_size=2)
        self.assertEqual([row["id"] for row in rows], ["1", "2"])
        self.assertEqual(session.calls[1][1]["params"]["skip"], 2)

    def test_synergy_missing_event_id_is_rejected(self):
        session = FakeSession([FakeResponse({"data": [{}]})])
        provider = providers.SportradarSynergyProvider(
            providers.ProviderConfig(api_key="test"), session)
        with self.assertRaises(providers.ProviderSchemaError):
            provider.player_report("g", "t")

    def test_canonical_play_type_mapping_and_provenance(self):
        provider = providers.SportradarSynergyProvider(providers.ProviderConfig(api_key="test"))
        events = [{"id": "e1", "oPlayer": {"id": "p1"}, "plays": ["PandRRollMan"],
                   "points": 2, "fgMade": 1, "fgAttempt": 1, "shotX": 35, "shotY": 71}]
        result = provider.canonicalize(events, 2025, "g1")
        possession = next(item for item in result if item.field == "play_type_possessions")
        self.assertEqual(possession.dimensions["play_type"], "pick_and_roll_roll_man")
        self.assertEqual(possession.provenance.provider, "sportradar_synergy")
        self.assertEqual(possession.provenance.player_id, "p1")
        self.assertEqual(possession.provenance.season, "2025")
        self.assertEqual(possession.provenance.game_id, "g1")
        self.assertEqual(possession.provenance.evidence_type, "DIRECT")

    def test_player_and_season_reconciliation_skip_unidentified_event(self):
        provider = providers.SportradarSynergyProvider(providers.ProviderConfig(api_key="test"))
        result = provider.canonicalize([{"id": "e", "plays": ["Iso"]}], "2024-25", "g")
        self.assertEqual(result, [])

    def test_fallback_selection_and_source_confidence(self):
        proxy = providers.HoopRFallbackProvider.rim_attack_proxy("1", 2025, 3, 10)
        direct = providers.CanonicalFeature("drives", 8, providers.Provenance(
            "nba_stats", "player_track", "drives", "2025", "1", None, "now", 10,
            "player-season", "official", "DIRECT"))
        self.assertIs(providers.choose_feature([proxy, direct]), direct)
        self.assertGreater(providers.source_confidence("nba_stats", "DIRECT"),
                           providers.source_confidence("hoopr", "PROXY"))

    def test_proxy_is_not_labeled_as_drive_count(self):
        feature = providers.HoopRFallbackProvider.rim_attack_proxy("1", 2025, 4, 8)
        self.assertEqual(feature.field, "rim_attack_proxy")
        self.assertEqual(feature.provenance.evidence_type, "PROXY")

    def test_shadow_comparison_never_promotes(self):
        feature = providers.HoopRFallbackProvider.rim_attack_proxy("1", 2025, 4, 8)
        result = providers.shadow_comparison(70, 74, feature)
        self.assertEqual(result["difference"], 4)
        self.assertFalse(result["promoted"])
        self.assertEqual(result["mode"], "shadow")

    def test_source_aware_fallback_levels(self):
        proxy = providers.HoopRFallbackProvider.rim_attack_proxy("1", 2025, 4, 8)
        self.assertEqual(providers.fallback_level([proxy]), "C")
        self.assertEqual(providers.fallback_level([]), "NOT_TRACKED")


if __name__ == "__main__":
    unittest.main()
