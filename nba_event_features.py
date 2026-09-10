"""Validated, locally cached NBA event features derived from hoopR play-by-play."""

import json
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).with_name("data") / "nba_event_features.json"


@lru_cache(maxsize=1)
def snapshot():
    if not DATA_PATH.exists():
        return {"status": "not_loaded", "players": {}, "coverage": {}, "sources": []}
    try:
        with DATA_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, TypeError):
        return {"status": "invalid", "players": {}, "coverage": {}, "sources": []}
    required = {"status", "players", "coverage", "sources"}
    if not required.issubset(data) or not isinstance(data["players"], dict):
        return {"status": "invalid", "players": {}, "coverage": {}, "sources": []}
    return data


def features_for_player(stats_player_id):
    return snapshot()["players"].get(str(stats_player_id), {})


def clear_cache():
    snapshot.cache_clear()
