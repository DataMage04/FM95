"""Integrated consistency validation, deliberately not statistical calibration.

Run: python -m fm95.analysis.validation --matches 8 --json
Each scenario is replayed with identical inputs and management decisions.
"""
import argparse
from dataclasses import asdict
import hashlib
import json

from fm95.players.attributes import Attributes
from fm95.match.simulation import run_match
from fm95.players.demo import demo_team
from fm95.match import Match,Phase
from fm95.match.systems.injuries import InjuryConfig
from fm95.match.mechanics.offside import OffsideConfig
from fm95.match.spatial.positions import Position
from fm95.match.systems.roles import Duty
from fm95.match.systems.substitution_policy import AutoSubstitutionConfig
from fm95.match.tactics import preset
from fm95.match.systems.timekeeping import AddedTimeConfig
from fm95.match.mechanics.woodwork import WoodworkConfig
from fm95.players.factory import generate_team
from fm95.players.decisions import DecisionConfig


def require(condition,message):
    if not condition:raise AssertionError(message)


def validate_state(match):
    ids=set()
    for team in (match.home,match.away):
        active=match.active_players(team.id)
        require(len({p.id for p in active})==len(active),'Duplicate active player')
        ids.update(p.id for p in active)
        if active:require(sum(p.is_goalkeeper for p in active)==1,'Goalkeeper count')
        for point in match.player_locations(team.id).values():
            require(0<=point.x<=1 and 0<=point.y<=1,'Player outside pitch')
        for condition in match.conditions(team.id).values():
            require(0<=condition.energy<=1,'Invalid condition')
    if match.possession is not None:
        require(match.possession.player_id in ids,'Inactive carrier')
    if match.pending_restart is not None:
        require(match.pending_restart.taker_id in ids,'Inactive restart taker')
    if match.phase not in (Phase.FULL_TIME,Phase.ABANDONED,Phase.HALF_TIME):
        require(sum(x is not None for x in (match.possession,match.loose_ball,match.pending_restart))==1,'Incoherent ball state')
    require(match.period_timing.restart_delay_seconds>=0,'Negative delay')


def validate_statistics(match):
    stats=[match.statistics(team.id) for team in (match.home,match.away)]
    require(sum(s.possession_seconds for s in stats)+match.loose_ball_seconds+match.dead_ball_seconds==match.elapsed_seconds,'Clock reconciliation')
    require((stats[0].goals,stats[1].goals)==(match.home_goals,match.away_goals),'Score reconciliation')
    for own,other in ((stats[0],stats[1]),(stats[1],stats[0])):
        require(own.shots_on_target==own.goals-own.own_goals_received-own.deflection_goals+other.saves,'Shots on target')
        require(own.passes_attempted-own.passes_completed==other.interceptions+own.misplaced_passes+own.passes_out+own.passes_offside,'Pass reconciliation')
        require(own.own_goals==other.own_goals_received,'Own-goal reconciliation')
        require(own.offsides+own.restart_second_touches+own.indirect_rule_offences==other.indirect_free_kicks_awarded,'Indirect restart reconciliation')
        require(own.expected_goals>=0 and own.shots>=own.shots_on_target,'Shot bounds')
        require(own.substitutions<=match.substitution_config.max_substitutions,'Substitution budget')
        probabilities=[e.goal_probability for e in match.events if e.team_id==own.team_id and
            e.kind in ('goal','shot_saved','shot_missed','shot_blocked','shot_parried','shot_woodwork') and e.goal_probability is not None]
        require(abs(own.expected_goals-sum(probabilities))<1e-9,'xG reconciliation')


def signature(match):
    payload={'events':[asdict(e) for e in match.events],
             'conditions':{t.id:{pid:asdict(c) for pid,c in match.conditions(t.id).items()} for t in (match.home,match.away)},
             'locations':{t.id:{pid:asdict(p) for pid,p in match.player_locations(t.id).items()} for t in (match.home,match.away)}}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()


def scenario(seed,index,profile=None,*,generated_squads=False,decision_strength=.5):
    from fm95.analysis.calibration import profile_configs
    styles=('balanced','pressing','possession','direct')
    if generated_squads:
        low,high=(.1,.9) if index>=4 else (.3,.7)
        home=generate_team('home','Home',seed=seed,team_strength=high if index%2==0 else low)
        away=generate_team('away','Away',seed=seed,team_strength=low if index%2==0 else high)
    else:
        home_attributes=Attributes(passing=.8 if index%2==0 else .2,stamina=.3) if index>=4 else Attributes()
        away_attributes=Attributes(passing=.2 if index%2==0 else .8,stamina=.9) if index>=4 else Attributes()
        home=demo_team('home','Home',include_bench=True,attributes=home_attributes)
        away=demo_team('away','Away',include_bench=True,attributes=away_attributes)
    match=Match(home,away,seed=seed,decision_config=DecisionConfig(decision_strength),
        home_tactics=preset(styles[index%4]),away_tactics=preset(styles[(index+1)%4]),
        injury_config=InjuryConfig(enabled=True,temporary_probability=.5),
        auto_substitution_config=AutoSubstitutionConfig(enabled=True),added_time_config=AddedTimeConfig(enabled=True),
        woodwork_config=WoodworkConfig(enabled=True),offside_config=OffsideConfig(screening_enabled=True),
        **profile_configs(profile or {}))
    originals=match.home,match.away
    active_home=match.active_players('home')
    striker=next(p for p in active_home if p.position==Position.ST)
    midfielder=next(p for p in active_home if p.position in (Position.CM,Position.AM))
    match.set_player_duty('home',striker.id,Duty.ATTACK)
    match.set_player_duty('home',midfielder.id,Duty.SUPPORT)
    match.start()
    checks=0
    while match.phase not in (Phase.FULL_TIME,Phase.ABANDONED):
        if match.phase==Phase.HALF_TIME:
            active=match.active_players('home')
            outfield=[p for p in active if not p.is_goalkeeper]
            formation=match.formation('home')
            if outfield:
                formation[outfield[-1].id]=Position.AM
                match.set_formation('home',formation)
                match.set_player_duty('home',outfield[-1].id,Duty.SUPPORT)
            bench=[p for p in match.available_substitutes('home') if not p.is_goalkeeper]
            if bench and outfield and match.substitution_status('home').remaining:
                match.substitute('home',outfield[0].id,bench[0].id)
            match.resume()
        else:
            if match.elapsed_seconds==600 and len(match.active_players('home'))>=9:
                player=next(p for p in match.active_players('home') if not p.is_goalkeeper)
                match.treat_player('home',player.id,reason='validation_treatment')
            if match.elapsed_seconds==1200 and len(match.active_players('away'))>=9:
                player=next(p for p in match.active_players('away') if not p.is_goalkeeper)
                match.issue_card('away',player.id,'red')
            match.step()
        validate_state(match);checks+=1
    validate_statistics(match)
    require((match.home,match.away)==originals,'Natural squad mutation')
    player_decisions=sum(event.kind=='player_decision' for event in match.events)
    press_attempts=sum(event.kind.startswith('press_') for event in match.events)
    substitutions=sum(event.kind=='substitution' for event in match.events)
    return match,checks,{'player_decision_events':player_decisions,
                         'press_attempts':press_attempts,'substitutions':substitutions}


def run_validation(matches=8,seed=95,profile=None,*,generated_squads=False,decision_strength=.5):
    if type(matches) is not int or matches<1 or type(seed) is not int:raise ValueError('Positive match count and integer seed required.')
    if type(generated_squads) is not bool:raise ValueError('generated_squads must be boolean.')
    DecisionConfig(decision_strength)
    rows=[]
    for index in range(matches):
        first,checks,features=scenario(seed+index,index,profile,
            generated_squads=generated_squads,decision_strength=decision_strength)
        second,replay_checks,_=scenario(seed+index,index,profile,
            generated_squads=generated_squads,decision_strength=decision_strength)
        digest=signature(first)
        require(digest==signature(second),'Replay divergence')
        rows.append({'seed':seed+index,'attribute_range_stress':index>=4,'phase':first.phase.value,'elapsed_seconds':first.elapsed_seconds,
                     'state_checks':checks+replay_checks,'replay_sha256':digest,**features,
                     'temporary_treatments':sum(first.statistics(t.id).temporary_treatments for t in (first.home,first.away)),
                     'treatment_returns':sum(first.statistics(t.id).treatment_returns for t in (first.home,first.away)),
                     'woodwork_contacts':sum(first.statistics(t.id).woodwork_contacts for t in (first.home,first.away))})
    if generated_squads:
        require(sum(row['player_decision_events'] for row in rows)>0,'No player decision choices were exercised')
        require(sum(row['press_attempts'] for row in rows)>0,'No player pressing choices were exercised')
        require(sum(row['substitutions'] for row in rows)>0,'No generated-player substitutions were exercised')
    return {'passed':True,'purpose':'consistency and determinism; no calibration',
            'scenarios':matches,'simulations':2*matches,'base_seed':seed,'parameters':profile or {},
            'player_differentiation':{'enabled':generated_squads,'decision_strength':decision_strength,
                                      'synthetic_strength_range':[.1,.9] if generated_squads else None},
            'features':{'added_time':True,'woodwork':True,'temporary_treatment':True,'off_ball_screening':True,'automatic_substitutions':True},
            'player_decision_events':sum(row['player_decision_events'] for row in rows),
            'press_attempts':sum(row['press_attempts'] for row in rows),
            'substitutions':sum(row['substitutions'] for row in rows),
            'completed':sum(r['phase']=='full_time' for r in rows),'abandoned':sum(r['phase']=='abandoned' for r in rows),
            'state_checks':sum(r['state_checks'] for r in rows),'results':rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matches',type=int,default=8);parser.add_argument('--seed',type=int,default=95)
    parser.add_argument('--profile',choices=('prototype','pl2015'),default='prototype')
    parser.add_argument('--generated-squads',action='store_true',help='Validate role-shaped synthetic players and their choices')
    parser.add_argument('--decision-strength',type=float,default=.5)
    parser.add_argument('--json',action='store_true');args=parser.parse_args()
    from fm95.analysis.calibration import load_profile
    result=run_validation(args.matches,args.seed,load_profile() if args.profile=='pl2015' else None,
                          generated_squads=args.generated_squads,decision_strength=args.decision_strength)
    print(json.dumps(result,indent=2) if args.json else f"Passed {result['simulations']} simulations and {result['state_checks']} state checks.")

if __name__=='__main__':main()
