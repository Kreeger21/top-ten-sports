"""Optional official-NBA feature cache used by the franchise attribute model."""

import json
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).with_name("data") / "nba_official_features.json"


@lru_cache(maxsize=1)
def snapshot():
    if not DATA_PATH.exists():
        return {"status": "not_loaded", "players": {}, "sources": []}
    try:
        with DATA_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, TypeError):
        return {"status": "invalid", "players": {}, "sources": []}
    return data if isinstance(data.get("players"), dict) else {"status": "invalid", "players": {}, "sources": []}


def features_for_player(stats_player_id):
    return snapshot().get("players", {}).get(str(stats_player_id), {})


def clear_cache():
    snapshot.cache_clear()
