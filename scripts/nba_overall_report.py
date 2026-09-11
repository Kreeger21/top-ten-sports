"""Generate reusable before/after NBA Overall calibration artifacts."""
import csv,json,statistics,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nba_franchise_service as franchise
import nba_overall_service as model

OLD_WEIGHTS={"scoring":.25,"playmaking":.17,"rebounding":.15,"steal_hands":.10,"rim_protection":.13,"finishing":.20}
def old(profile):
 r={x["id"]:x["rating"] for x in profile.get("attributes",())}; v=[(r[k],w) for k,w in OLD_WEIGHTS.items() if k in r]
 return round(sum(x*w for x,w in v)/sum(w for _,w in v)) if v else None
def percentile(values,p):
 s=sorted(values); return s[round((len(s)-1)*p)] if s else 0
def main():
 rows=[];seen=set()
 for team in franchise.TEAMS:
  for player in franchise.roster(team.code):
   if player["player_id"] in seen or not player.get("attribute_profile"):continue
   seen.add(player["player_id"]); debug=model.calculate(player["attribute_profile"],player["position"],True)
   old_value=old(player["attribute_profile"])
   if not debug or old_value is None: continue
   rows.append({"player_id":player["player_id"],"player_name":player["name"],"team":team.code,"position":player["position"],"broad_position":player.get("broad_position",player["position"]),"position_source":player.get("position_source"),"old_overall":old_value,"new_overall":debug["overall"],"attribute_model_version":player["attribute_profile"]["model_version"],"overall_model_version":model.OVERALL_MODEL_VERSION,"model_coverage":debug["coverage"],"overall_confidence":debug["confidence"],"core_penalty":debug["core_penalty"],"versatility_bonus":debug["versatility_bonus"],"skill_groups":debug["groups"]})
 for key in ("old","new"):
  ranked=sorted(rows,key=lambda x:(-x[f"{key}_overall"],x["player_name"]))
  for rank,row in enumerate(ranked,1):row[f"{key}_rank"]=rank
 for row in rows:row["overall_change"]=row["new_overall"]-row["old_overall"];row["rank_change"]=row["old_rank"]-row["new_rank"]
 out=Path(__file__).resolve().parents[1]/"reports";out.mkdir(exist_ok=True)
 flat=[{k:v for k,v in row.items() if k!="skill_groups"} for row in rows]
 with (out/"nba_overall_before_after.csv").open("w",newline="",encoding="utf-8") as f:w=csv.DictWriter(f,fieldnames=flat[0]);w.writeheader();w.writerows(flat)
 diagnostics={}
 for pos in ("ALL","G","F","C"):
  group=rows if pos=="ALL" else [r for r in rows if r["broad_position"]==pos];values=[r["new_overall"] for r in group]
  diagnostics[pos]={"count":len(values),"mean":round(statistics.mean(values),2),"median":statistics.median(values),"stdev":round(statistics.pstdev(values),2),**{f"p{int(p*100)}":percentile(values,p) for p in (.1,.25,.5,.75,.9,.95)},**{f"count_{n}_plus":sum(v>=n for v in values) for n in (70,75,80,85,90,95)}}
 payload={"players":rows,"distribution":diagnostics,"top_50":sorted(rows,key=lambda x:-x["new_overall"])[:50],"bottom_20":sorted(rows,key=lambda x:x["new_overall"])[:20]}
 (out/"nba_overall_diagnostics.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
 print(json.dumps(diagnostics,indent=2));print("TOP 20");print("\n".join(f'{r["new_rank"]:>3} {r["player_name"]:<28} {r["position"]} {r["new_overall"]}' for r in payload["top_50"][:20]))
if __name__=="__main__":main()
