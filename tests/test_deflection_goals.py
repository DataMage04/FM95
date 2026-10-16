from dataclasses import replace
import unittest
from unittest.mock import patch

from fm95.actions import ActionConfig
from fm95.boundaries import Boundary, BoundaryExit
from fm95.defending import DefenseConfig, Pressure
from fm95.demo import demo_team
from fm95.goals import crosses_goal_mouth
from fm95.match import Match, Phase
from fm95.pitch import Location, Pitch
from fm95.shooting import ShotConfig


class DeflectionGoalTests(unittest.TestCase):
    def make_match(self, **kwargs):
        match = Match(demo_team('h','Home'),demo_team('a','Away'),seed=95,**kwargs)
        match.start()
        return match

    def test_metric_mouth_both_lines_posts_and_touchlines(self):
        for pitch in (Pitch(),Pitch(width=50,goal_width=6)):
            for boundary,x in ((Boundary.LEFT,0),(Boundary.RIGHT,1)):
                self.assertTrue(crosses_goal_mouth(BoundaryExit(boundary,Location(x,.5)),pitch))
                for y in (.5-pitch.goal_width/(2*pitch.width),.5+pitch.goal_width/(2*pitch.width),.1):
                    self.assertFalse(crosses_goal_mouth(BoundaryExit(boundary,Location(x,y)),pitch))
            self.assertFalse(crosses_goal_mouth(BoundaryExit(Boundary.TOP,Location(.5,1)),pitch))

    def test_own_goals_credit_opponent_at_both_ends_and_after_switch(self):
        for second_half in (False,True):
            for team in ('h','a'):
                match = self.make_match()
                if second_half:
                    match.phase = Phase.HALF_TIME
                    match.resume()
                own_end = 0 if int(match.attacking_direction(team))==1 else 1
                boundary = Boundary.RIGHT if own_end else Boundary.LEFT
                match.resolve_deflection_exit(BoundaryExit(boundary,Location(own_end,.5)),team,team+'-3')
                opponent = 'a' if team=='h' else 'h'
                event = match.events[-2]
                self.assertEqual((event.kind,event.team_id,event.player_id,event.last_touch_team_id),
                                 ('own_goal',opponent,team+'-3',team))
                self.assertEqual(match.statistics(opponent).goals,1)
                self.assertEqual(match.statistics(opponent).own_goals_received,1)
                self.assertEqual(match.statistics(team).own_goals,1)
                self.assertEqual(match.statistics(opponent).shots,0)
                self.assertEqual(match.statistics(opponent).expected_goals,0)
                self.assertEqual(match.possession.team_id,team)
                self.assertIsNone(match.pending_restart)
                self.assertIsNone(match.loose_ball)
                self.assertIsNone(match.transition)

    def test_other_end_goal_without_inventing_a_shot(self):
        match = self.make_match()
        match.resolve_deflection_exit(BoundaryExit(Boundary.RIGHT,Location(1,.5)),'h','h-3')
        stats = match.statistics('h')
        self.assertEqual((stats.goals,stats.deflection_goals,stats.shots,stats.shots_on_target),(1,1,0,0))
        self.assertEqual(match.events[-2].kind,'deflection_goal')

    def test_non_goal_routes_and_invalid_requests_are_atomic(self):
        match = self.make_match()
        match.resolve_deflection_exit(BoundaryExit(Boundary.RIGHT,Location(1,.8)),'a','a-3')
        self.assertEqual(match.pending_restart.kind,'corner')
        self.assertEqual(match.home_goals,0)
        before = (tuple(match.events),match.pending_restart,match.home_goals)
        for exit,team,pid in ((None,'a','a-3'),(BoundaryExit(Boundary.RIGHT,Location(1,.5)),'a','h-3')):
            with self.assertRaises(ValueError):
                match.resolve_deflection_exit(exit,team,pid)
            self.assertEqual((tuple(match.events),match.pending_restart,match.home_goals),before)
        match.phase = Phase.FULL_TIME
        with self.assertRaises(RuntimeError):
            match.resolve_deflection_exit(BoundaryExit(Boundary.RIGHT,Location(1,.5)),'a','a-3')

    def test_parried_shot_can_enter_goal_without_second_shot_or_double_score(self):
        match = self.make_match(defense_config=DefenseConfig(enabled=False),
            action_config=ActionConfig(on_target_probability=1,goal_given_on_target_probability=0),
            shot_config=ShotConfig(block_probability=0,parry_probability=1))
        match.set_possession('h','h-9',location=Location(.8,.5))
        with patch('fm95.match.rebound_endpoint',return_value=(1.01,.5)):
            match._play_shot(match.possession,match._active_team('h'),match._active_team('a'),Pressure(None,None,0))
        self.assertEqual([e.kind for e in match.events[-3:]],['goal','goal_attribution','kickoff'])
        home,away = match.statistics('h'),match.statistics('a')
        self.assertEqual((home.goals,home.shots,home.shots_on_target,away.saves,away.own_goals),(1,1,1,0,0))
        self.assertEqual(home.expected_goals,0)
        self.assertEqual(match.home_goals,1)

    def test_blocked_shot_deflection_uses_blockers_last_touch(self):
        match = self.make_match(defense_config=DefenseConfig(enabled=False),
            shot_config=ShotConfig(block_probability=1),action_config=ActionConfig(on_target_probability=0))
        match.set_possession('a','a-3',location=Location(.9,.5))
        match.set_possession('h','h-9',location=Location(.8,.5))
        with patch('fm95.match.rebound_endpoint',return_value=(1.01,.5)):
            match._play_shot(match.possession,match._active_team('h'),match._active_team('a'),Pressure(None,None,0))
        self.assertEqual(match.events[-2].player_id,'a-3')
        self.assertEqual(match.statistics('h').shots_blocked,1)
        self.assertEqual(match.statistics('a').blocks,1)
        self.assertEqual(match.statistics('h').shots_on_target,0)
        self.assertEqual(match.home_goals,1)

    def test_on_target_block_continuation_is_credited_to_shooter_once(self):
        match=self.make_match(defense_config=DefenseConfig(enabled=False),
            action_config=ActionConfig(on_target_probability=1),shot_config=ShotConfig(block_probability=1))
        match.set_possession('a','a-3',location=Location(.9,.5))
        match.set_possession('h','h-9',location=Location(.8,.5))
        with patch('fm95.match.rebound_endpoint',return_value=(1.01,.5)):
            match._play_shot(match.possession,match._active_team('h'),match._active_team('a'),Pressure(None,None,0))
        goal=next(e for e in match.events if e.kind=='goal')
        self.assertEqual((goal.player_id,goal.deflector_id),('h-9','a-3'))
        self.assertEqual((match.statistics('h').goals,match.statistics('h').shots),(1,1))
        self.assertEqual(match.statistics('a').own_goals,0)
