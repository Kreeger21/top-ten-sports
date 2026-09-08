"""Create a reviewed-at-build-time bridge between ESPN and historical player IDs."""

import csv
from collections import defaultdict
from pathlib import Path
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
ROSTERS = ROOT / "data" / "nba_franchise_rosters.csv"
STATS = ROOT / "data" / "nba_franchise_stats_2025.csv"
OUTPUT = ROOT / "data" / "nba_player_identity.csv"


def normalize(value):
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return "".join(character for character in plain.casefold() if character.isalnum())


def main():
    with STATS.open(encoding="utf-8") as handle:
        stat_rows = tuple(csv.DictReader(handle))
    candidates = defaultdict(set)
    for row in stat_rows:
        candidates[normalize(row["player"])].add(row["player_id"])
    with ROSTERS.open(encoding="utf-8") as handle:
        roster_rows = tuple(csv.DictReader(handle))
    output = []
    for row in roster_rows:
        matches = candidates.get(normalize(row["name"]), set())
        output.append({"espn_player_id": row["player_id"], "stats_player_id": next(iter(matches)) if len(matches) == 1 else "",
                       "match_method": "exact_normalized_name" if len(matches) == 1 else "unmatched",
                       "review_status": "auto_verified" if len(matches) == 1 else "needs_review"})
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=output[0].keys())
        writer.writeheader()
        writer.writerows(output)
    matched = sum(bool(row["stats_player_id"]) for row in output)
    print(f"Mapped {matched} of {len(output)} current roster records to stable historical IDs")


if __name__ == "__main__":
    main()
