"""Position-aware NBA Overall model; universal attribute ratings remain untouched."""
from math import exp

OVERALL_MODEL_VERSION = "v2-positional-value"
CORE_PENALTY_STRENGTH = 1.8
CORE_COMPETENCY = 65
VERSATILITY_THRESHOLD = 82
VERSATILITY_STRENGTH = .055
CURVE_CENTER = 61
CURVE_SCALE = 13
HYBRID_PRIMARY_WEIGHT = .7
# Universal percentiles make role-specialist center box-score skills structurally
# abundant. These league-calibrated offsets align positional value baselines without
# changing any attribute or imposing ranking quotas.
POSITION_BASELINE_OFFSETS = {"G": 0, "F": 2.5, "C": -8.0}
EVIDENCE_QUALITY = {"DIRECT_HIGH":1.0,"DIRECT_MEDIUM":.85,"DERIVED_HIGH":.8,"DERIVED_MEDIUM":.65,"PROXY":.4,"FALLBACK":.25}
GROUP_EVIDENCE = {"finishing":"DERIVED_MEDIUM","shooting":"DIRECT_HIGH","shot_creation":"DERIVED_MEDIUM","playmaking":"DIRECT_MEDIUM","ball_handling":"DERIVED_MEDIUM","off_ball":"PROXY","post_offense":"DERIVED_MEDIUM","transition":"DERIVED_MEDIUM","rebounding":"DIRECT_HIGH","perimeter_defense":"FALLBACK","interior_defense":"PROXY","rim_protection":"DIRECT_MEDIUM","defensive_playmaking":"DIRECT_MEDIUM","hustle":"FALLBACK","screening":"FALLBACK"}
SKILL_GROUPS = {
    "finishing": {"finishing": 1}, "shooting": {"overall_shooting": .45, "three_point_shooting": .35, "free_throw_shooting": .20},
    "shot_creation": {"possession_self_creation": .45, "self_created_scoring": .25, "scoring_volume": .30},
    "playmaking": {"playmaking": 1}, "ball_handling": {"handle_security": .50, "turnover_avoidance": .30, "assist_turnover": .20},
    "off_ball": {"off_ball_scoring": .50, "scoring": .30, "finishing": .20}, "post_offense": {"hook_scoring": .55, "post_possession_scoring": .45},
    "transition": {"transition_scoring": 1}, "rebounding": {"rebounding": 1},
    "perimeter_defense": {"steal_hands": .75, "rim_protection": .25},
    "interior_defense": {"rim_protection": .8, "rebounding": .2},
    "rim_protection": {"rim_protection": 1}, "defensive_playmaking": {"steal_hands": 1},
    "hustle": {"steal_hands": .5, "rebounding": .5}, "screening": {"finishing": .4, "rebounding": .6},
}
POSITION_MODELS = {
 "G": {"weights":{"finishing":.12,"shooting":.13,"shot_creation":.16,"playmaking":.16,"ball_handling":.15,"off_ball":.07,"transition":.05,"perimeter_defense":.09,"defensive_playmaking":.04,"rebounding":.02,"interior_defense":.01},"core":("ball_handling","playmaking","shot_creation","shooting")},
 "F": {"weights":{"finishing":.14,"shooting":.11,"shot_creation":.11,"playmaking":.08,"ball_handling":.06,"off_ball":.08,"transition":.07,"rebounding":.11,"perimeter_defense":.09,"interior_defense":.07,"rim_protection":.04,"defensive_playmaking":.04},"core":("finishing","shooting","shot_creation","perimeter_defense")},
 "C": {"weights":{"finishing":.17,"post_offense":.09,"rebounding":.17,"interior_defense":.14,"rim_protection":.14,"screening":.08,"off_ball":.07,"playmaking":.05,"shooting":.04,"transition":.03,"ball_handling":.02},"core":("finishing","rebounding","interior_defense","rim_protection")},
}

def _groups(profile):
    ratings={x["id"]:x["rating"] for x in (*profile.get("attributes",()),*profile.get("granular_attributes",()))}
    result={}
    for group, sources in SKILL_GROUPS.items():
        valid=[(ratings[k],w) for k,w in sources.items() if k in ratings]
        if valid: result[group]=sum(v*w for v,w in valid)/sum(w for _,w in valid)
    return result

def _position(position):
    return {"PG":"G","SG":"G","SF":"F","PF":"F"}.get(position,position)

def calculate(profile, position="F", debug=False):
    raw_positions=(position or "F").replace("-","/").split("/")
    positions=[_position(item) for item in raw_positions if _position(item) in POSITION_MODELS] or ["F"]
    pos=positions[0]
    model=POSITION_MODELS.get(pos,POSITION_MODELS["F"]); groups=_groups(profile)
    effective={g:65+(value-65)*EVIDENCE_QUALITY[GROUP_EVIDENCE[g]] for g,value in groups.items()}
    valid=[(g,w) for g,w in model["weights"].items() if g in effective]
    if not valid:return None if not debug else {}
    base=sum(effective[g]*w for g,w in valid)/sum(w for _,w in valid)
    deficits=[max(0,CORE_COMPETENCY-effective[g]) for g in model["core"] if g in effective]
    penalty=sum((d/25)**1.7 for d in deficits)*CORE_PENALTY_STRENGTH
    bonuses=[max(0,v-VERSATILITY_THRESHOLD) for g,v in groups.items() if g not in model["core"]]
    bonus=sum(bonuses)*VERSATILITY_STRENGTH
    raw=base-penalty+bonus+POSITION_BASELINE_OFFSETS[pos]
    if len(positions)>1 and positions[1] != pos:
        secondary=calculate(profile,positions[1],True)
        raw=HYBRID_PRIMARY_WEIGHT*raw+(1-HYBRID_PRIMARY_WEIGHT)*secondary["raw_score"]
    overall=round(25+74/(1+exp(-(raw-CURVE_CENTER)/CURVE_SCALE)))
    coverage=round(sum(w for g,w in model["weights"].items() if g in groups)*100)
    quality=round(sum(w*EVIDENCE_QUALITY[GROUP_EVIDENCE[g]] for g,w in valid)/sum(w for _,w in valid)*100)
    result={"overall":overall,"position":"/".join(positions),"groups":groups,"effective_groups":effective,"group_evidence":GROUP_EVIDENCE,"weights":model["weights"],"raw_score":round(raw,2),"core_penalty":round(penalty,2),"versatility_bonus":round(bonus,2),"coverage":coverage,"direct_data_coverage":quality,"tracking_data_coverage":0,"confidence":"High" if quality>=80 else "Medium" if quality>=55 else "Low","model_version":OVERALL_MODEL_VERSION}
    return result if debug else overall
