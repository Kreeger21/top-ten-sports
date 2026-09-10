"""Incremental, resumable NBA game-level tracking downloader."""

import argparse
import json
from pathlib import Path
import random
import sys
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
import nba_tracking_warehouse as warehouse

HEADERS = {"Accept": "application/json, text/plain, */*", "Origin": "https://www.nba.com",
           "Referer": "https://www.nba.com/", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"}


def fetch(session, game_id, kind, timeout=30, retries=2):
    url = "https://stats.nba.com/stats/" + warehouse.ENDPOINTS[kind]
    error = None
    for attempt in range(retries + 1):
        try:
            response = session.get(url, params={"GameID": game_id}, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").casefold()
            if "json" not in content_type or response.text.lstrip().startswith("<"):
                raise ValueError("official endpoint returned non-JSON content")
            payload = response.json()
            warehouse.validate_payload(payload, game_id, kind)
            return payload
        except (requests.RequestException, ValueError) as exc:
            error = exc
            if attempt < retries: time.sleep((2 ** attempt) + random.uniform(.25, .75))
    raise RuntimeError(f"{kind} failed for {game_id}: {error}")


def ingest(game_ids, season, kinds, force=False, timeout=30, retries=2, pace=1.25):
    report = {kind: {"requested": 0, "downloaded": 0, "skipped": 0, "failed": 0, "errors": []} for kind in kinds}
    with requests.Session() as session:
        for game_id in game_ids:
            if not (str(game_id).isdigit() and len(str(game_id)) == 10): raise ValueError(f"invalid game ID: {game_id}")
            for kind in kinds:
                target = warehouse.cache_path(game_id, kind); report[kind]["requested"] += 1
                if target.exists() and not force:
                    report[kind]["skipped"] += 1; continue
                try:
                    wrapper = warehouse.save_validated(fetch(session, str(game_id), kind, timeout, retries), game_id, season, kind)
                    report[kind]["downloaded"] += 1
                    print(f"cached {kind} {wrapper['game_id']} ({len(wrapper['rows'])} rows)", flush=True)
                except (RuntimeError, ValueError) as exc:
                    report[kind]["failed"] += 1; report[kind]["errors"].append(str(exc))
                time.sleep(pace + random.uniform(0, .4))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-id", action="append", required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--kind", action="append", choices=warehouse.ENDPOINTS, default=[])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()
    kinds = args.kind or list(warehouse.ENDPOINTS)
    report = ingest(args.game_id, args.season, kinds, args.force, args.timeout, args.retries)
    diagnostics_path = ROOT / "data" / "nba_tracking_diagnostics.json"
    prior = {"runs": []}
    if diagnostics_path.exists():
        try:
            prior = json.loads(diagnostics_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    prior.setdefault("runs", []).append({"season": args.season, "game_ids": args.game_id, "report": report})
    prior["runs"] = prior["runs"][-50:]
    warehouse.atomic_json(diagnostics_path, prior)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__": main()
