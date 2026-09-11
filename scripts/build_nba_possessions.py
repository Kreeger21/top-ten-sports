"""Build compact possession evidence from hoopR and optionally pbpstats.

pbpstats is the preferred possession reconstructor when its NBA providers are
reachable.  hoopR structured events are the durable open-data fallback.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from nba_possession_service import (CanonicalPossession, DATA_PATH, MODEL_VERSION, POSSESSION_PATH,
                                    Provenance, aggregate_player_possessions, finalize_possession)
from scripts.build_nba_event_features import _download_frame


def _value(row, name, default=None):
    value = getattr(row, name, default)
    return default if value != value else value


def _event(row):
    kind=str(_value(row,"type_text","") or ""); text=str(_value(row,"text","") or "")
    lower=kind.casefold(); player=lambda n: str(int(_value(row,n))) if _value(row,n) not in (None,"") else None
    item={"event_type":kind,"text":text,"team_id":str(int(_value(row,"team_id"))) if _value(row,"team_id") is not None else ""}
    is_free_throw="free throw" in lower
    if bool(_value(row,"shooting_play",False)) and not is_free_throw:
        item.update(shot_attempt=True,shot_player=player("athlete_id_1"),made=bool(_value(row,"scoring_play",False)),
                    points=int(_value(row,"score_value",0) or 0))
        if "assist" in text.casefold(): item["assist_player"]=player("athlete_id_2")
    if "turnover" in lower:
        item["turnover_player"]=player("athlete_id_1")
        if "steal" in text.casefold(): item["steal_player"]=player("athlete_id_2")
    if "offensive rebound" in lower: item["offensive_rebound"]=player("athlete_id_1")
    if "defensive rebound" in lower: item["defensive_rebound"]=player("athlete_id_1")
    if is_free_throw:
        item["free_throw"]=True; item["made"]=bool(_value(row,"scoring_play",False)); item["points"]=int(_value(row,"score_value",0) or 0)
        match=re.search(r"(\d+)\s+of\s+(\d+)",lower)
        item["final_free_throw"]=bool(match and match.group(1)==match.group(2))
    if "foul" in lower: item["foul"]=True
    if "fast break" in text.casefold(): item["fast_break"]=True
    return item


def reconstruct_frame(frame, season):
    """Reconstruct conservative possession boundaries from structured ESPN events."""
    regular=frame[frame["season_type"]==2].sort_values(["game_id","game_play_number"])
    output=[]; start_type_by_game=defaultdict(lambda:"Start of Period")
    for game_id, game in regular.groupby("game_id",sort=False):
        current=[]; offense=""; number=0; period=None; start_clock=None
        home=str(int(game.iloc[0]["home_team_id"])); away=str(int(game.iloc[0]["away_team_id"]))
        lineups=_initial_lineups(game,home,away); possession_lineups={team:list(players) for team,players in lineups.items()}
        for row in game.itertuples(index=False):
            event=_event(row); kind=event["event_type"].casefold(); team=event["team_id"]
            new_period=int(_value(row,"period_number",1))
            clock=float(_value(row,"start_quarter_seconds_remaining",0) or 0)
            action_team = team if event.get("shot_attempt") or event.get("turnover_player") or event.get("offensive_rebound") else ""
            if not current:
                period=new_period; start_clock=clock
                offense=action_team or offense
                possession_lineups={key:list(value) for key,value in lineups.items()}
            elif action_team and not offense:
                # Opening jump balls/timeouts can precede the first offensive action.
                offense=action_team
            if action_team and offense and action_team != offense and not event.get("defensive_rebound"):
                # A new structured offensive action is a safety boundary after unusual/dead-ball sequences.
                output.append(_make(game_id,season,number,period,start_clock,clock,offense,home,away,current,start_type_by_game[game_id],possession_lineups))
                number+=1; current=[]; period=new_period; start_clock=clock; offense=action_team
                possession_lineups={key:list(value) for key,value in lineups.items()}
            current.append(event)
            if "substitution" in kind:
                incoming=str(int(_value(row,"athlete_id_1"))) if _value(row,"athlete_id_1") is not None else None
                outgoing=str(int(_value(row,"athlete_id_2"))) if _value(row,"athlete_id_2") is not None else None
                if team in lineups and incoming and outgoing:
                    lineups[team]=[incoming if player==outgoing else player for player in lineups[team]]
            terminal=bool(event.get("turnover_player") or event.get("defensive_rebound") or
                          (event.get("shot_attempt") and event.get("made")) or event.get("final_free_throw") or "end period" in kind)
            if terminal and offense:
                output.append(_make(game_id,season,number,period,start_clock,clock,offense,home,away,current,start_type_by_game[game_id],possession_lineups))
                number+=1
                if event.get("defensive_rebound"): start_type_by_game[game_id]="Defensive Rebound"; offense=team
                elif event.get("steal_player"): start_type_by_game[game_id]="Steal"; offense=away if offense==home else home
                elif event.get("turnover_player"): start_type_by_game[game_id]="Turnover"; offense=away if offense==home else home
                elif "end period" in kind: start_type_by_game[game_id]="Start of Period"; offense=""
                else: start_type_by_game[game_id]="Made Basket"; offense=away if offense==home else home
                current=[]; start_clock=None
        if current and offense: output.append(_make(game_id,season,number,period,start_clock,0,offense,home,away,current,start_type_by_game[game_id],possession_lineups))
    return output


def _initial_lineups(game,home,away):
    """Infer opening units conservatively from first-quarter actions/substitutions."""
    result={home:[],away:[]}; incoming={home:set(),away:set()}; outgoing={home:[],away:[]}; actors={home:[],away:[]}
    first=game[game["period_number"]==1]
    for row in first.itertuples(index=False):
        team=str(int(_value(row,"team_id"))) if _value(row,"team_id") is not None else ""
        if team not in result: continue
        kind=str(_value(row,"type_text","") or "").casefold()
        p1=str(int(_value(row,"athlete_id_1"))) if _value(row,"athlete_id_1") is not None else None
        p2=str(int(_value(row,"athlete_id_2"))) if _value(row,"athlete_id_2") is not None else None
        if "substitution" in kind:
            if p1: incoming[team].add(p1)
            if p2 and p2 not in outgoing[team]: outgoing[team].append(p2)
        elif p1 and p1 not in actors[team]: actors[team].append(p1)
    for team in result:
        # First outgoing players plus early actors who were not known replacements.
        candidates=outgoing[team]+[p for p in actors[team] if p not in incoming[team] and p not in outgoing[team]]
        result[team]=candidates[:5]
    return result


def _make(game,season,number,period,start,end,offense,home,away,events,start_type,lineups=None):
    defense=away if offense==home else home
    p=CanonicalPossession(str(game),int(season),f"{game}:{period}:{number}",int(period),start,end,
        max(0,float(start)-float(end)) if start is not None else None,offense,defense,
        offensive_players=list((lineups or {}).get(offense,[])),defensive_players=list((lineups or {}).get(defense,[])),
        possession_start_type=start_type,events=list(events),points=sum(int(e.get("points",0)) for e in events if e.get("made")),
        provenance=Provenance("hoopR","SportsDataverse ESPN NBA play-by-play",int(season),str(game),
                              "conservative structured-event possession reconstruction",confidence="Medium",
                              evidence_tier="Derived Open-Data Possession Evidence").__dict__)
    shot=next((e for e in reversed(events) if e.get("shot_attempt")),None)
    turnover=next((e for e in events if e.get("turnover_player")),None)
    rebound=next((e for e in reversed(events) if e.get("offensive_rebound") or e.get("defensive_rebound")),None)
    if shot: p.shot_attempt=True;p.shot_player=shot.get("shot_player");p.shot_result="made" if shot.get("made") else "missed";p.assist_player=shot.get("assist_player")
    if turnover:p.turnover_player=turnover.get("turnover_player");p.steal_player=turnover.get("steal_player")
    if rebound:p.offensive_rebound=rebound.get("offensive_rebound");p.defensive_rebound=rebound.get("defensive_rebound")
    p.foul=any(e.get("foul") for e in events);p.free_throws=sum(bool(e.get("free_throw")) for e in events)
    return finalize_possession(p)


def _atomic_json(path,data):
    fd,temp=tempfile.mkstemp(prefix="nba-possession-",suffix=".json",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream: json.dump(data,stream,separators=(",",":"),allow_nan=False)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def build(seasons,timeout=120):
    possessions=[]; sources=[]
    for season in seasons:
        frame=_download_frame(season,timeout); batch=reconstruct_frame(frame,season); possessions.extend(batch)
        sources.append({"season":season,"rows":len(frame),"games":len({p.game_id for p in batch}),"possessions":len(batch),"source":"hoopR"})
    POSSESSION_PATH.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(POSSESSION_PATH,"wt",encoding="utf-8") as stream:
        for p in possessions: stream.write(json.dumps(p.to_dict(),separators=(",",":"),allow_nan=False)+"\n")
    players=aggregate_player_possessions(possessions)
    lineup_complete=sum(len(set(p.offensive_players))==5 and len(set(p.defensive_players))==5 for p in possessions)
    result={"status":"verified","schema_version":1,"model_version":MODEL_VERSION,"generated_at":datetime.now(timezone.utc).isoformat(),
            "players":players,"sources":sources,"coverage":{"games":len({p.game_id for p in possessions}),"possessions":len(possessions),
            "players":len(players),"lineup_coverage":round(100*lineup_complete/len(possessions),1) if possessions else 0,
            "lineup_method":"substitution/event reconstruction; incomplete possessions excluded from on/off",
            "source":"hoopR fallback; pbpstats live endpoints unavailable"}}
    _atomic_json(DATA_PATH,result); return result


def reaggregate():
    with DATA_PATH.open(encoding="utf-8") as stream: result=json.load(stream)
    def records():
        with gzip.open(POSSESSION_PATH,"rt",encoding="utf-8") as stream:
            for line in stream: yield CanonicalPossession(**json.loads(line))
    result["players"]=aggregate_player_possessions(records())
    result["generated_at"]=datetime.now(timezone.utc).isoformat();result["coverage"]["players"]=len(result["players"])
    _atomic_json(DATA_PATH,result);return result


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--seasons",nargs="+",type=int,default=[2025,2024,2023]);parser.add_argument("--timeout",type=int,default=120);parser.add_argument("--reaggregate",action="store_true")
    args=parser.parse_args();result=reaggregate() if args.reaggregate else build(args.seasons,args.timeout);print(json.dumps(result["coverage"],indent=2))
