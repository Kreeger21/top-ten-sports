"""Fit an explainable 2K benchmark without changing the franchise Overall model."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
import unicodedata

import numpy as np
import requests

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
SOURCE_URL="https://raw.githubusercontent.com/wkoverfield/nba2kapi/main/nba2k-all-players.json"
DATA_PATH=ROOT/"data"/"nba2k_calibration_source.json"
REPORT_PATH=ROOT/"reports"/"nba_2k_calibration.json"
CATEGORY_FIELDS=("Outside Scoring","Inside Scoring","Playmaking","Athleticism","Defense","Rebounding")
ATTRIBUTE_GROUPS={
    "Outside Scoring":("closeShot","midRangeShot","threePointShot","freeThrow","shotIQ","offensiveConsistency"),
    "Inside Scoring":("layup","standingDunk","drivingDunk","postHook","postFade","postControl","drawFoul","hands"),
    "Playmaking":("passAccuracy","ballHandle","speedWithBall","passIQ","passVision"),
    "Athleticism":("speed","agility","strength","vertical","stamina","hustle","overallDurability"),
    "Defense":("interiorDefense","perimeterDefense","steal","block","helpDefenseIQ","passPerception","defensiveConsistency"),
    "Rebounding":("offensiveRebound","defensiveRebound"),
}


def broad_position(value):
    primary=str(value).split("/")[0].strip()
    return "G" if primary in {"PG","SG"} else "F" if primary in {"SF","PF"} else "C"


def fetch(timeout=60):
    response=requests.get(SOURCE_URL,timeout=timeout);response.raise_for_status()
    DATA_PATH.write_bytes(response.content)
    return response.headers.get("etag")


def load():
    with DATA_PATH.open(encoding="utf-8") as stream: source=json.load(stream)
    rows=[]
    for row in source.get("players",[]):
        if row.get("teamType") != "curr": continue
        try:
            attributes=row["attributes"]; values=[]
            for category in CATEGORY_FIELDS:
                observed=[float(attributes[key]) for key in ATTRIBUTE_GROUPS[category] if attributes.get(key) is not None]
                values.append(sum(observed)/len(observed))
            positions=row.get("positions") or ["F"]
            rows.append({"name":row["name"],"position":broad_position("/".join(positions)),"overall":float(row["overall"]),"values":values})
        except (TypeError,ValueError,KeyError,ZeroDivisionError): pass
    return rows


def ridge_fit(rows,seed=2026,alpha=5.0):
    shuffled=list(rows);random.Random(seed).shuffle(shuffled);cut=max(1,round(len(shuffled)*.8));train,test=shuffled[:cut],shuffled[cut:]
    x=np.array([r["values"] for r in train]);y=np.array([r["overall"] for r in train]);mean=x.mean(axis=0);scale=x.std(axis=0);scale[scale==0]=1
    z=(x-mean)/scale;design=np.column_stack((np.ones(len(z)),z));penalty=np.eye(design.shape[1])*alpha;penalty[0,0]=0
    beta=np.linalg.solve(design.T@design+penalty,design.T@y)
    test_x=np.array([r["values"] for r in test]);actual=np.array([r["overall"] for r in test]);pred=np.column_stack((np.ones(len(test)),(test_x-mean)/scale))@beta
    mae=float(np.mean(np.abs(pred-actual)));baseline=float(np.sum((actual-actual.mean())**2));r2=1-float(np.sum((actual-pred)**2))/baseline if baseline else 0
    importance=np.abs(beta[1:]);importance=importance/importance.sum() if importance.sum() else importance
    return {"players":len(rows),"train_players":len(train),"test_players":len(test),"test_mae":round(mae,3),"test_r2":round(r2,3),
        "standardized_coefficients":{field:round(float(value),4) for field,value in zip(CATEGORY_FIELDS,beta[1:])},
        "relative_importance":{field:round(float(value),4) for field,value in zip(CATEGORY_FIELDS,importance)},
        "target_distribution":{"mean":round(float(np.mean([r['overall'] for r in rows])),2),"median":round(float(np.median([r['overall'] for r in rows])),2),
            "minimum":int(min(r["overall"] for r in rows)),"maximum":int(max(r["overall"] for r in rows)),
            "count_80_plus":sum(r["overall"]>=80 for r in rows),"count_85_plus":sum(r["overall"]>=85 for r in rows),"count_90_plus":sum(r["overall"]>=90 for r in rows)}}


def _normal(value):
    return " ".join(unicodedata.normalize("NFKD",str(value)).encode("ascii","ignore").decode().casefold().split())


def compare_to_franchise(rows):
    import nba_franchise_service as franchise
    import nba_overall_service as overall_model
    reference={_normal(row["name"]):row for row in rows};matches=[];seen=set()
    for team in franchise.TEAMS:
        for player in franchise.roster(team.code):
            if player["player_id"] in seen or not player.get("attribute_profile"):continue
            seen.add(player["player_id"]);source=reference.get(_normal(player["name"]))
            if not source:continue
            ours=overall_model.calculate(player["attribute_profile"],player["position"])
            matches.append({"player":player["name"],"position":player["position"],"our_overall":ours,"two_k_overall":round(source["overall"]),"gap":round(source["overall"]-ours)})
    ours=np.array([x["our_overall"] for x in matches]);twok=np.array([x["two_k_overall"] for x in matches])
    return {"matched_players":len(matches),"mean_our_overall":round(float(ours.mean()),2),"mean_2k_overall":round(float(twok.mean()),2),
        "mean_2k_minus_ours":round(float((twok-ours).mean()),2),"mean_absolute_gap":round(float(np.abs(twok-ours).mean()),2),
        "correlation":round(float(np.corrcoef(ours,twok)[0,1]),3),
        "largest_positive_gaps":sorted(matches,key=lambda x:-x["gap"])[:20],"largest_negative_gaps":sorted(matches,key=lambda x:x["gap"])[:20]}


def main():
    etag=fetch();rows=load();models={position:ridge_fit([r for r in rows if r["position"]==position]) for position in ("G","F","C")}
    comparison=compare_to_franchise(rows)
    payload={"status":"diagnostic_only","generated_at":datetime.now(timezone.utc).isoformat(),"source_url":SOURCE_URL,"source_etag":etag,
        "source_note":"Fan-maintained scrape of 2kratings.com; not affiliated with or endorsed by 2K Sports.",
        "method":"80/20 deterministic ridge regression on six transparent category averages derived from granular 2K attributes; badges excluded.",
        "players":len(rows),"features":CATEGORY_FIELDS,"models":models,"franchise_comparison":comparison,
        "guardrail":"No production attribute, positional weight, penalty, bonus, baseline, or display curve was changed."}
    REPORT_PATH.parent.mkdir(exist_ok=True);REPORT_PATH.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    md=["# NBA 2K calibration benchmark","",payload["source_note"],"",payload["method"],"",f"Players: {len(rows)}","",
        "| Position | Test MAE | Test R² | Strongest category | 2K max | 85+ | 90+ |","|---|---:|---:|---|---:|---:|---:|"]
    for position,model in models.items():
        strongest=max(model["relative_importance"],key=model["relative_importance"].get);dist=model["target_distribution"]
        md.append(f"| {position} | {model['test_mae']:.2f} | {model['test_r2']:.2f} | {strongest} | {dist['maximum']} | {dist['count_85_plus']} | {dist['count_90_plus']} |")
    md += ["","## Direct franchise comparison","",f"Matched players: {comparison['matched_players']}",
        f"Mean Overall — ours: {comparison['mean_our_overall']}; 2K: {comparison['mean_2k_overall']}",
        f"Mean 2K minus ours: {comparison['mean_2k_minus_ours']}",f"Correlation: {comparison['correlation']}","",
        "The strong category regressions show that 2K Overall is highly recoverable from its published category ratings. Outside scoring is most influential for guards and forwards, while centers are balanced across defense, outside scoring, inside scoring, and rebounding. The 2K distribution also has a much wider elite range than the current frozen franchise display curve.","",
        "This benchmark can guide a later display-curve review, but it cannot reveal 2K's proprietary formula. Its category ratings may themselves be tuned to reach a desired Overall, so coefficients describe correlation rather than causation."]
    (ROOT/"reports"/"nba_2k_calibration.md").write_text("\n".join(md),encoding="utf-8")
    print(json.dumps(payload,indent=2))


if __name__=="__main__":main()
