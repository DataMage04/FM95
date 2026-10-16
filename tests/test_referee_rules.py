import unittest
from dataclasses import replace
from fm95.demo import demo_team
from fm95.match import Match,Phase,Restart
from fm95.pitch import Location
from fm95.actions import ActionConfig
from fm95.rules import PenaltyIncident,PenaltyOffence,TouchKind,penalty_decision
from fm95.shooting import ShotConfig
from fm95.defending import DefenseConfig

class RefereeRuleTests(unittest.TestCase):
    def make_match(self):
        m=Match(demo_team('h','H'),demo_team('a','A'),seed=95,
            action_config=ActionConfig(interval_seconds=99999,foul_probability=0),
            defense_config=DefenseConfig(enabled=False),shot_config=ShotConfig(enabled=False))
        m.start();m.set_possession('h','h-9',location=Location(.8,.5))
        return m
    def penalty(self,m,offence,goal=1,impact=True):
        ball=Location(1-11/m.pitch.length,.5)
        m._possession=None;m._pending_restart=Restart('penalty','h','h-9',ball.zone,ball)
        m.set_piece_config=replace(m.set_piece_config,penalty_on_target_probability=1,penalty_goal_given_on_target_probability=goal)
        m.set_penalty_incident(PenaltyIncident(offence,impact=impact))
    def test_penalty_matrix(self):
        O=PenaltyOffence
        for offence,goal,expected in ((O.ACCIDENTAL_DOUBLE_TOUCH,1,'retake'),(O.ACCIDENTAL_DOUBLE_TOUCH,0,'indirect'),
            (O.ATTACKER_ENCROACHMENT,1,'retake'),(O.ATTACKER_ENCROACHMENT,0,'indirect'),
            (O.DEFENDER_ENCROACHMENT,1,'allow'),(O.DEFENDER_ENCROACHMENT,0,'retake'),
            (O.BOTH_ENCROACHMENT,1,'retake'),(O.BACKWARDS,1,'indirect'),(O.ILLEGAL_FEINT,0,'indirect'),
            (O.GOALKEEPER_OFF_LINE,0,'retake')):
            self.assertEqual(penalty_decision(PenaltyIncident(offence),'goal' if goal else 'shot_saved'),expected)
            m=self.make_match();self.penalty(m,offence,goal);m._play_action()
            if expected=='allow':self.assertEqual(m.home_goals,goal)
            else:
                self.assertEqual(m.home_goals,0)
                self.assertEqual(m.statistics('h').shots,0)
                self.assertEqual(m.pending_restart.kind,'penalty' if expected=='retake' else 'indirect_free_kick')
        self.assertEqual(penalty_decision(PenaltyIncident(O.ATTACKER_ENCROACHMENT,impact=False),'goal'),'allow')
        self.assertEqual(penalty_decision(PenaltyIncident(O.GOALKEEPER_OFF_LINE,impact=False),'shot_missed'),'allow')
    def test_penalty_retake_extends_period_and_preserves_second_half_length(self):
        m=self.make_match();m.elapsed_seconds=2699
        self.penalty(m,PenaltyOffence.ACCIDENTAL_DOUBLE_TOUCH)
        m.step();self.assertEqual(m.phase,Phase.FIRST_HALF);self.assertEqual(m.pending_restart.kind,'penalty')
        m.step();self.assertEqual(m.phase,Phase.HALF_TIME);self.assertEqual(m.home_goals,1)
        self.assertEqual(m.elapsed_seconds,2701)
        m.resume();self.assertEqual(m.period_timing.target_end_seconds,5401)
    def test_keeper_warning_then_caution(self):
        m=self.make_match()
        for _ in range(2):self.penalty(m,PenaltyOffence.GOALKEEPER_OFF_LINE,goal=0);m._play_action()
        self.assertEqual(m.statistics('a').yellow_cards,1)
        self.assertEqual(m.statistics('h').penalty_retakes,2)
    def test_handling_pass_header_throw_and_release(self):
        for kind,recipient,illegal in ((TouchKind.KICK,'h-1',True),(TouchKind.THROW,None,True),
                                       (TouchKind.HEADER,None,False),(TouchKind.KICK,'h-7',False)):
            m=self.make_match();p=Location(.05,.5)
            m.record_ball_touch('h','h-7',p,kind=kind,recipient_id=recipient)
            self.assertEqual(m.handle_ball('h','h-1',p),not illegal)
            if illegal:self.assertEqual(m.pending_restart.kind,'indirect_free_kick')
        m=self.make_match();p=Location(.05,.5)
        self.assertTrue(m.handle_ball('h','h-1',p));m.release_keeper_ball('h','h-1',p)
        self.assertFalse(m.handle_ball('h','h-1',p))
        m=self.make_match();m.record_ball_touch('h','h-7',p,kind=TouchKind.KICK,recipient_id='h-1')
        m.keeper_attempt_release('h','h-1',p);self.assertTrue(m.handle_ball('h','h-1',p))
    def test_handball_area_and_eight_seconds(self):
        for pid,p,kind in (('h-7',Location(.05,.5),'penalty'),('h-1',Location(.5,.5),'free_kick')):
            m=self.make_match();self.assertFalse(m.handle_ball('h',pid,p));self.assertEqual(m.pending_restart.kind,kind)
        m=self.make_match();m.handle_ball('h','h-1',Location(.05,.5))
        for _ in range(9):m.step()
        self.assertEqual(m.pending_restart.kind,'corner');self.assertEqual(m.statistics('h').keeper_time_violations,1)
    def test_restart_retake_and_handover(self):
        for kind,offence,expected in (('throw_in','foul_throw','throw_in'),('goal_kick','delay','corner'),
                                      ('free_kick','wall_distance','indirect_free_kick')):
            m=self.make_match();p=Location(.2,0)
            m._possession=None;m._pending_restart=Restart(kind,'h','h-7',p.zone,p)
            m.restart_offence(offence,'h','h-7');self.assertEqual(m.pending_restart.kind,expected)
            self.assertEqual(m.pending_restart.team_id,'a')

    def test_wrong_kicker_and_quick_interception_decisions(self):
        m=self.make_match();self.penalty(m,PenaltyOffence.BACKWARDS)
        with self.assertRaises(ValueError):m.set_penalty_incident(PenaltyIncident(PenaltyOffence.WRONG_KICKER))
        m.set_penalty_incident(PenaltyIncident(PenaltyOffence.WRONG_KICKER,player_id='h-7'))
        m._play_action()
        self.assertEqual(m.discipline('h','h-7').yellow_cards,1)
        self.assertEqual(m.pending_restart.kind,'indirect_free_kick')
        m=self.make_match();p=Location(.5,.5)
        m._possession=None;m._pending_restart=Restart('free_kick','h','h-7',p.zone,p)
        before=m.pending_restart
        m.restart_offence('quick_interception','a','a-7',impact=True)
        self.assertEqual(m.pending_restart,before)
        self.assertEqual(m.events[-1].kind,'restart_advantage')
