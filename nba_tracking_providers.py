"""Provider-agnostic canonical NBA tracking features.

Adapters in this module are deliberately shadow-only. They normalize licensed or
cached inputs, but do not alter the active player-rating model.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
from typing import Any, Iterable, Mapping

import requests


CANONICAL_FIELDS = frozenset({
    "drives", "drive_fgm", "drive_fga", "drive_points", "drive_fta",
    "drive_assists", "drive_passes", "drive_turnovers", "passes_made",
    "passes_received", "potential_assists", "secondary_assists",
    "assist_points_created", "touches", "time_of_possession",
    "rebound_chances", "offensive_rebound_chances", "defensive_rebound_chances",
    "deflections", "charges_drawn", "loose_balls_recovered", "screen_assists",
    "screen_assist_points", "matchup_possessions", "matchup_fgm", "matchup_fga",
    "matchup_fg3m", "matchup_fg3a", "matchup_turnovers", "matchup_blocks",
    "matchup_switches", "help_blocks", "help_fgm", "help_fga",
    "rim_defended_fgm", "rim_defended_fga", "shot_x", "shot_y", "rim_attack_proxy",
    "play_type_possessions", "play_type_points", "play_type_fgm",
    "play_type_fga", "play_type_turnovers", "play_type_fouls",
})

PLAY_TYPES = {
    "Iso": "isolation", "PostUp": "post_up",
    "PandRBallHandler": "pick_and_roll_ball_handler",
    "PandRRollMan": "pick_and_roll_roll_man", "Cut": "cut",
    "Transition": "transition", "SpotUp": "spot_up",
    "Offensive Rebound": "offensive_rebound", "OffScreen": "off_screen",
    "HandOff": "handoff",
}


class ProviderUnavailable(RuntimeError):
    """A provider cannot be used safely in the current configuration."""


class ProviderSchemaError(ValueError):
    """A provider response no longer matches its validated schema."""


@dataclass(frozen=True)
class ProviderConfig:
    api_key: str | None = None
    access_level: str = "trial"
    timeout: float = 20.0

    def __post_init__(self):
        if self.access_level not in {"trial", "production"}:
            raise ValueError("access_level must be trial or production")

    @classmethod
    def from_env(cls, key_name="SPORTRADAR_API_KEY"):
        return cls(api_key=os.getenv(key_name),
                   access_level=os.getenv("SPORTRADAR_ACCESS_LEVEL", "trial").lower(),
                   timeout=float(os.getenv("SPORTRADAR_TIMEOUT_SECONDS", "20")))


@dataclass(frozen=True)
class Provenance:
    provider: str
    provider_dataset: str
    provider_field: str
    season: str
    player_id: str
    game_id: str | None
    retrieved_at: str
    sample: float
    coverage: str
    access_tier: str | None
    evidence_type: str


@dataclass(frozen=True)
class CanonicalFeature:
    field: str
    value: float
    provenance: Provenance
    dimensions: Mapping[str, str] | None = None

    def __post_init__(self):
        if self.field not in CANONICAL_FIELDS:
            raise ValueError(f"unknown canonical field: {self.field}")

    def as_dict(self):
        return {"field": self.field, "value": self.value,
                "provenance": asdict(self.provenance),
                "dimensions": dict(self.dimensions or {})}


SOURCE_CONFIDENCE = {
    ("nba_stats", "DIRECT"): 1.0,
    ("sportradar_nba", "DIRECT"): .95,
    ("sportradar_synergy", "DIRECT"): .92,
    ("sportradar_synergy", "DERIVED"): .84,
    ("hoopr", "DERIVED"): .78,
    ("hoopr", "PROXY"): .55,
}


def source_confidence(provider: str, evidence_type: str) -> float:
    return SOURCE_CONFIDENCE.get((provider, evidence_type), 0.0)


class _HTTPProvider:
    provider_name = "provider"

    def __init__(self, config=None, session=None):
        self.config = config or ProviderConfig.from_env()
        self.session = session or requests.Session()

    def _get(self, url, params=None):
        if not self.config.api_key:
            raise ProviderUnavailable(f"{self.provider_name} credential is not configured")
        try:
            response = self.session.get(url, params=params or {},
                                        headers={"x-api-key": self.config.api_key},
                                        timeout=self.config.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderUnavailable(f"{self.provider_name} request failed") from exc
        if not isinstance(payload, dict):
            raise ProviderSchemaError("provider response must be an object")
        return payload


class SportradarNBAProvider(_HTTPProvider):
    """Official Sportradar NBA v8 adapter; no undocumented tracking mappings."""

    provider_name = "sportradar_nba"
    base_url = "https://api.sportradar.com/nba/{access}/v8/en"

    def game_play_by_play(self, game_id):
        url = self.base_url.format(access=self.config.access_level) + f"/games/{game_id}/pbp.json"
        return self._get(url)

    def game_summary(self, game_id):
        url = self.base_url.format(access=self.config.access_level) + f"/games/{game_id}/summary.json"
        return self._get(url)


class NBAStatsProvider:
    """Read-only adapter over the existing verified official NBA cache."""

    provider_name = "nba_stats"
    field_map = {
        "reboundChancesTotal": "rebound_chances",
        "reboundChancesOffensive": "offensive_rebound_chances",
        "reboundChancesDefensive": "defensive_rebound_chances",
        "touches": "touches", "secondaryAssists": "secondary_assists",
        "passes": "passes_made", "deflections": "deflections",
        "chargesDrawn": "charges_drawn", "screenAssists": "screen_assists",
        "screenAssistPoints": "screen_assist_points",
        "partialPossessions": "matchup_possessions",
        "matchupFieldGoalsMade": "matchup_fgm",
        "matchupFieldGoalsAttempted": "matchup_fga",
        "matchupThreePointersMade": "matchup_fg3m",
        "matchupThreePointersAttempted": "matchup_fg3a",
        "matchupTurnovers": "matchup_turnovers", "matchupBlocks": "matchup_blocks",
        "switchesOn": "matchup_switches", "helpBlocks": "help_blocks",
        "helpFieldGoalsMade": "help_fgm", "helpFieldGoalsAttempted": "help_fga",
        "defendedAtRimFieldGoalsMade": "rim_defended_fgm",
        "defendedAtRimFieldGoalsAttempted": "rim_defended_fga",
    }

    def features_for_player(self, player_id, season="weighted-2023-2025"):
        import nba_tracking_warehouse
        sources = nba_tracking_warehouse.aggregate().get("players", {}).get(str(player_id), {})
        now, result = datetime.now(timezone.utc).isoformat(), []
        for dataset, values in sources.items():
            sample = values.get("unique_games", 0)
            for vendor_field, field in self.field_map.items():
                if vendor_field in values:
                    result.append(CanonicalFeature(field, float(values[vendor_field]), Provenance(
                        self.provider_name, dataset, vendor_field, str(season), str(player_id), None,
                        now, float(sample), "verified-cache", "official", "DIRECT")))
        return result


class SportradarSynergyProvider(_HTTPProvider):
    """Synergy possession-event adapter with independent provenance."""

    provider_name = "sportradar_synergy"
    base_url = "https://api.sportradar.com/synergy/basketball"

    def __init__(self, config=None, session=None):
        super().__init__(config or ProviderConfig.from_env("SPORTRADAR_SYNERGY_API_KEY"), session)

    def player_report(self, game_id, team_id, page_size=100):
        path = f"/nba/games/{game_id}/teams/{team_id}/events/reports/player"
        skip, rows, seen = 0, [], set()
        while True:
            payload = self._get(self.base_url + path, {"skip": skip, "take": page_size})
            page = payload.get("data")
            if not isinstance(page, list):
                raise ProviderSchemaError("Synergy response is missing data[]")
            for event in page:
                event_id = str(event.get("id") or event.get("eventId") or "")
                if not event_id:
                    raise ProviderSchemaError("Synergy event is missing an ID")
                if event_id not in seen:
                    seen.add(event_id); rows.append(event)
            if len(page) < page_size:
                break
            skip += page_size
        return rows

    def canonicalize(self, events: Iterable[Mapping[str, Any]], season, game_id):
        now = datetime.now(timezone.utc).isoformat()
        features = []
        for event in events:
            player = event.get("oPlayer") or {}
            player_id = str(player.get("id") or event.get("oPlayerId") or "")
            play_values = event.get("plays") or []
            if isinstance(play_values, str):
                play_values = [play_values]
            play_type = next((PLAY_TYPES[p] for p in play_values if p in PLAY_TYPES), None)
            if not player_id or not play_type:
                continue
            common = dict(provider=self.provider_name, provider_dataset="possession_events",
                          season=str(season), player_id=player_id, game_id=str(game_id),
                          retrieved_at=now, coverage="event", access_tier=self.config.access_level)
            dimensions = {"play_type": play_type, "side": "offense"}
            raw = {
                "play_type_possessions": (1, "plays", "DIRECT"),
                "play_type_points": (event.get("points", 0), "points", "DIRECT"),
                "play_type_fgm": (event.get("fgMade", 0), "fgMade", "DIRECT"),
                "play_type_fga": (event.get("fgAttempt", 0), "fgAttempt", "DIRECT"),
                "play_type_turnovers": (event.get("turnover", 0), "turnover", "DIRECT"),
                "play_type_fouls": (event.get("shootingFoul", 0), "shootingFoul", "DIRECT"),
            }
            for field, (value, vendor_field, evidence) in raw.items():
                features.append(CanonicalFeature(field, float(value or 0),
                    Provenance(provider_field=vendor_field, sample=1, evidence_type=evidence, **common), dimensions))
            for field, vendor_field in (("shot_x", "shotX"), ("shot_y", "shotY")):
                if event.get(vendor_field) is not None:
                    features.append(CanonicalFeature(field, float(event[vendor_field]),
                        Provenance(provider_field=vendor_field, sample=1, evidence_type="DIRECT", **common), dimensions))
        return features


class HoopRFallbackProvider:
    provider_name = "hoopr"

    @staticmethod
    def rim_attack_proxy(player_id, season, rim_attempts, total_attempts):
        if not total_attempts:
            return None
        provenance = Provenance("hoopr", "play_by_play_shots", "rim_fga/shot_fga",
            str(season), str(player_id), None, datetime.now(timezone.utc).isoformat(),
            float(total_attempts), "player-season", "open-source", "PROXY")
        return CanonicalFeature("rim_attack_proxy", float(rim_attempts) / float(total_attempts), provenance,
                                {"label": "rim_attack_proxy"})


def choose_feature(candidates, priority=("nba_stats", "sportradar_nba", "sportradar_synergy", "hoopr")):
    """Select explicitly by source priority; never silently relabel the source."""
    order = {provider: index for index, provider in enumerate(priority)}
    valid = [item for item in candidates if isinstance(item, CanonicalFeature)]
    return min(valid, key=lambda item: order.get(item.provenance.provider, len(order))) if valid else None


def shadow_comparison(old_rating, new_rating, feature=None):
    return {"mode": "shadow", "old_rating": old_rating, "new_rating": new_rating,
            "difference": None if old_rating is None or new_rating is None else new_rating - old_rating,
            "source": feature.provenance.provider if feature else "unavailable",
            "confidence": source_confidence(feature.provenance.provider,
                                             feature.provenance.evidence_type) if feature else 0.0,
            "promoted": False}


def fallback_level(features: Iterable[CanonicalFeature]):
    """Describe evidence strength without claiming lower tiers equal direct tracking."""
    providers = {item.provenance.provider for item in features}
    if "nba_stats" in providers or "sportradar_nba" in providers:
        return "A"
    if "sportradar_synergy" in providers:
        return "B"
    if providers:
        return "C"
    return "NOT_TRACKED"
