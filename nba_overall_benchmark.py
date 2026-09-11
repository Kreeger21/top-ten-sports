"""Optional external calibration for NBA franchise Overall ratings.

The franchise attribute model remains the source of detailed scouting grades.  A
locally refreshed 2K benchmark is used only to calibrate the single Overall number
for players that can be matched confidently by normalized full name.
"""
from functools import lru_cache
import json
from pathlib import Path
import unicodedata


SOURCE = Path(__file__).with_name("data") / "nba2k_calibration_source.json"


def _name(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(char for char in value if not unicodedata.combining(char)).casefold().split())


@lru_cache(maxsize=1)
def ratings():
    try:
        payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    rows = payload if isinstance(payload, list) else payload.get("players", ())
    result = {}
    for row in rows:
        name = _name(row.get("name"))
        overall = row.get("overall")
        if name and isinstance(overall, (int, float)) and row.get("teamType", "curr") == "curr":
            result[name] = int(round(overall))
    return result


def calibrated_overall(player_name, modeled_overall):
    """Return a benchmark-calibrated Overall, or the model result when unmatched."""
    benchmark = ratings().get(_name(player_name))
    if benchmark is None:
        return modeled_overall
    # Reserve 99 for the benchmark's very top tier while preserving separation
    # throughout the rest of its established rating curve.
    return min(99, benchmark + 1) if benchmark >= 97 else benchmark
