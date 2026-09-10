"""Developer-readable coverage and quality report for NBA attribute inputs."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import nba_attribute_service as attributes
import nba_event_features
import nba_tracking_warehouse
import nba_tracking_providers


def report():
    event = nba_event_features.snapshot()
    population = attributes._player_features()
    definitions = (*attributes.ATTRIBUTE_DEFINITIONS, *attributes.TENDENCY_DEFINITIONS)
    feature_coverage = {}
    for definition in definitions:
        rated = sum(attributes._calculate(player, definition, tuple(population.values())) is not None
                    for player in population.values())
        feature_coverage[definition.id] = {
            "players": rated,
            "population": len(population),
            "coverage_pct": round(rated / len(population) * 100, 1) if population else 0,
            "source": definition.source,
        }
    tracking = nba_tracking_warehouse.aggregate()
    tracking_players = tracking.get("players", {})
    tracking_coverage = {}
    for kind in nba_tracking_warehouse.ENDPOINTS:
        covered = [sources[kind] for sources in tracking_players.values() if kind in sources]
        tracking_coverage[kind] = {
            **tracking.get("coverage", {}).get(kind, {"games_downloaded": 0}),
            "players_covered": len(covered),
            "minutes_covered": round(sum(item.get("tracked_minutes", 0) for item in covered), 1),
        }
    diagnostics_path = ROOT / "data" / "nba_tracking_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8")) if diagnostics_path.exists() else {"runs": []}
    matrix_path = ROOT / "data" / "nba_tracking_provider_matrix.json"
    provider_matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    return {
        "model_version": attributes.MODEL_VERSION,
        "reference_population": attributes.REFERENCE_POPULATION,
        "event_cache_status": event.get("status"),
        "event_cache": event.get("coverage", {}),
        "official_game_tracking": tracking_coverage,
        "official_tracking_diagnostics": diagnostics.get("runs", [])[-5:],
        "provider_shadow_mode": True,
        "provider_priority": ["nba_stats", "sportradar_nba", "sportradar_synergy", "hoopr", "not_tracked"],
        "canonical_tracking_fields": sorted(nba_tracking_providers.CANONICAL_FIELDS),
        "provider_availability": provider_matrix,
        "season_validation": event.get("sources", []),
        "features": feature_coverage,
        "not_tracked": [name for name in attributes.CATEGORY_DESCRIPTIONS
                        if not any(definition.category == name and feature_coverage[definition.id]["players"]
                                   for definition in definitions)],
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2))
