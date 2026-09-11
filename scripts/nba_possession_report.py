"""Generate possession-evidence coverage, validation, role and inflation diagnostics."""
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import nba_franchise_service as franchise
import nba_overall_service as overall
import nba_possession_service as possession


def main():
    snap=possession.snapshot(); players=[]; seen=set()
    for team in franchise.TEAMS:
        for player in franchise.roster(team.code):
            if player["player_id"] in seen or not player.get("attribute_profile"):continue
            seen.add(player["player_id"]); profile=player["attribute_profile"]
            debug=overall.calculate(profile,player["position"],True)
            evidence=possession.features_for_player(player["player_id"])
            granular={item["id"]:item for item in profile.get("granular_attributes",())}
            features=evidence.get("features",{})
            players.append({"player_id":player["player_id"],"player_name":player["name"],"position":player["position"],
                "overall":debug.get("overall"),"raw_score":debug.get("raw_score"),"shot_creation":debug.get("groups",{}).get("shot_creation"),
                "ball_handling":debug.get("groups",{}).get("ball_handling"),"transition":debug.get("groups",{}).get("transition"),
                "post_offense":debug.get("groups",{}).get("post_offense"),"creation_burden":features.get("creation_burden"),
                "role_context":features.get("role_context"),"unassisted_make_rate":features.get("unassisted_make_rate"),
                "possessions":evidence.get("counts",{}).get("offensive_possessions",0),
                "evidence_quality":debug.get("direct_data_coverage"),"formula_coverage":debug.get("coverage")})
    ranked=sorted(players,key=lambda p:(-p["overall"],p["player_name"]))
    for rank,p in enumerate(ranked,1):p["rank"]=rank
    burdens=sorted(p["creation_burden"] for p in players if p["creation_burden"] is not None)
    burden_median=statistics.median(burdens) if burdens else None
    flags=[]
    for p in ranked:
        reasons=[]
        if p["rank"]<=30 and burden_median is not None and p["creation_burden"] is not None and p["creation_burden"]<burden_median: reasons.append("top-30 Overall with below-median Creation Burden")
        if (p["shot_creation"] or 0)>85 and (p["unassisted_make_rate"] or 0)<.30: reasons.append("elite Shot Creation with low unassisted make share")
        if reasons:flags.append({**p,"reasons":reasons})
    classes={}; total=0
    # Stream the canonical store to validate classifier distributions without loading it all.
    import gzip
    with gzip.open(possession.POSSESSION_PATH,"rt",encoding="utf-8") as stream:
        for line in stream:
            item=json.loads(line);label=item["transition_class"];classes[label]=classes.get(label,0)+1;total+=1
    distribution={key:{"count":value,"share":round(value/total,4)} for key,value in sorted(classes.items())}
    cohorts={}
    for role in sorted({p["role_context"] for p in players if p["role_context"]}):
        group=[p for p in players if p["role_context"]==role]
        cohorts[role]={"players":len(group),**{field:round(statistics.mean(p[field] for p in group if p[field] is not None),2) for field in ("shot_creation","ball_handling","overall") if any(p[field] is not None for p in group)}}
    raw_ranked=sorted(players,key=lambda p:-p["raw_score"])
    payload={"model_version":possession.MODEL_VERSION,"coverage":snap.get("coverage",{}),"transition_distribution":distribution,
        "creation_burden_median":burden_median,"role_cohorts":cohorts,"low_role_inflation_flags":flags,
        "top_50":ranked[:50],"distribution":{"maximum_raw_score":max(p["raw_score"] for p in players),
            "maximum_overall":max(p["overall"] for p in players),"count_80_plus":sum(p["overall"]>=80 for p in players),
            "count_85_plus":sum(p["overall"]>=85 for p in players),"count_90_plus":sum(p["overall"]>=90 for p in players),
            "top_raw_score_gaps":[round(raw_ranked[i]["raw_score"]-raw_ranked[i+1]["raw_score"],2) for i in range(min(9,len(raw_ranked)-1))]}}
    out=ROOT/"reports";out.mkdir(exist_ok=True);(out/"nba_possession_diagnostics.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
    ty=next((p for p in ranked if p["player_name"]=="Ty Jerome"),None)
    lines=["# NBA possession evidence report","",f"- Games: {payload['coverage'].get('games',0):,}",f"- Possessions: {payload['coverage'].get('possessions',0):,}",
        f"- Players covered: {payload['coverage'].get('players',0):,}",f"- Complete reconstructed lineup coverage: {payload['coverage'].get('lineup_coverage',0)}%",
        f"- Maximum frozen-formula Overall: {payload['distribution']['maximum_overall']}",f"- 80+/85+/90+: {payload['distribution']['count_80_plus']}/{payload['distribution']['count_85_plus']}/{payload['distribution']['count_90_plus']}","",
        "## Ty Jerome", "", json.dumps(ty,indent=2) if ty else "Not in current roster population.","","## Transition validation","",json.dumps(distribution,indent=2),"",
        "## Low-role inflation flags","",f"{len(flags)} diagnostic flags; these are not rating penalties.","",
        "## Compression conclusion","",
        "Possession evidence reduced several role-inflation cases, but the maximum raw positional value remains below 79 and evidence quality remains limited by unavailable optical defense, screening, off-ball movement, and complete passing data. The frozen logistic display curve also maps that narrow raw range to a maximum of 84. A dedicated Overall display-curve calibration phase is now justified, but it should remain separate from evidence construction and retain these missing-evidence warnings."]
    (out/"nba_possession_report.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"coverage":payload["coverage"],"distribution":payload["distribution"],"transition":distribution,"ty_jerome":ty,"flags":len(flags)},indent=2))


if __name__=="__main__":main()
