from dataclasses import FrozenInstanceError, replace
import unittest
from unittest.mock import patch

from fm95.players.demo import demo_team
from fm95.match import Match, Phase, Possession, Restart
from fm95.match.spatial.pitch import Location, Direction
from fm95.match.systems.roles import Duty
from fm95.match.mechanics.transitions import TransitionConfig, transition_targets


class TransitionTests(unittest.TestCase):
    def make_match(self, **kwargs):
        match = Match(demo_team('h','Home',include_bench=True),
                      demo_team('a','Away',include_bench=True),seed=95,**kwargs)
        match.start()
        match.set_possession('h','h-7',location=Location(.5,.5))
        return match

    def test_turnover_snapshot_expiry_same_team_and_reversal(self):
        match = self.make_match()
        self.assertIsNone(match.transition)
        match.set_possession('a','a-7',location=Location(.51,.5))
        state = match.transition
        self.assertEqual((state.winning_team_id,state.losing_team_id,state.started_at),('a','h',0))
        with self.assertRaises(FrozenInstanceError):
            state.started_at = 1
        match.elapsed_seconds = 5
        match.set_possession('a','a-8',location=Location(.52,.5))
        self.assertEqual(match.transition,state)
        match.elapsed_seconds = 12
        self.assertIsNone(match.transition)
        match.set_possession('h','h-8',location=Location(.52,.5))
        self.assertEqual(match.transition.started_at,12)
        self.assertEqual(match.transition.losing_team_id,'a')

    def test_loose_ball_retains_prior_owner_and_clock(self):
        match = self.make_match()
        match.set_loose_ball(Location(.5,.5))
        self.assertIsNone(match.transition)
        def recovery(*args, **kwargs):
            match._possession = Possession('a','a-7',location=Location(.5,.5))
            match._loose_ball = None
        with patch.object(match,'_resolve_action',side_effect=recovery):
            match._play_action()
        self.assertEqual(match.transition.losing_team_id,'h')
        match.set_loose_ball(Location(.5,.5))
        match.elapsed_seconds = 13
        with patch.object(match,'_resolve_action',side_effect=recovery):
            match._play_action()
        self.assertIsNone(match.transition)

    def test_direct_action_turnover_is_observed_after_resolution(self):
        match = self.make_match()
        def intercept(*args, **kwargs):
            match._possession = Possession('a','a-7',location=Location(.5,.5))
        with patch.object(match,'_resolve_action',side_effect=intercept):
            match._play_action()
        self.assertEqual(match.transition.winning_team_id,'a')

    def test_restarts_kickoffs_halftime_and_disabled_state(self):
        match = self.make_match()
        match.set_possession('a','a-7',location=Location(.5,.5))
        match._pending_restart = Restart('throw_in','h','h-7',Location(.5,0).zone,Location(.5,0))
        self.assertIsNone(match.transition)
        def restart(*args, **kwargs):
            match._pending_restart = None
            match._possession = Possession('h','h-7',location=Location(.5,0))
        with patch.object(match,'_resolve_action',side_effect=restart):
            match._play_action()
        self.assertIsNone(match.transition)
        match._kickoff(match.away)
        self.assertIsNone(match.transition)
        match.phase = Phase.HALF_TIME
        self.assertIsNone(match.transition)
        match.resume()
        self.assertIsNone(match.transition)
        disabled = self.make_match(transition_config=TransitionConfig(enabled=False))
        disabled.set_possession('a','a-7',location=Location(.5,.5))
        self.assertIsNone(disabled.transition)

    def test_targets_move_forward_recover_and_mirror_without_boosting_keeper_or_hold(self):
        match = self.make_match()
        attackers,defenders = match.active_players('h'),match.active_players('a')
        anchors = match.formation_reference_locations('a')
        targets = {**match.formation_reference_locations('h'),**anchors}
        targets['a-3'] = Location(.5,.8)
        locations = {**match.player_locations('h'),**match.player_locations('a')}
        duties = {'h-6':Duty.DEFEND}
        def calculate(direction, points, refs, actual, ball):
            return transition_targets(attackers,defenders,points,refs,actual,'h-7',ball,
                direction,match.pitch,duties,1,TransitionConfig())
        result = calculate(Direction.RIGHT,targets,anchors,locations,Location(.5,.5))
        self.assertGreater(result['h-9'].x,targets['h-9'].x)
        for pid in ('h-1','h-3','h-4','h-6','h-7','a-1'):
            self.assertEqual(result[pid],targets[pid])
        self.assertLess(match.pitch.distance(result['a-3'],anchors['a-3']),
                        match.pitch.distance(targets['a-3'],anchors['a-3']))
        rotate = lambda points: {pid:p.rotated() for pid,p in points.items()}
        mirror = calculate(Direction.LEFT,rotate(targets),rotate(anchors),rotate(locations),Location(.5,.5))
        for pid in result:
            self.assertAlmostEqual(mirror[pid].x,result[pid].rotated().x)
            self.assertAlmostEqual(mirror[pid].y,result[pid].rotated().y)
        neutral = transition_targets(attackers,defenders,targets,anchors,locations,'h-7',Location(.5,.5),
                                    Direction.RIGHT,match.pitch,duties,0,TransitionConfig())
        self.assertEqual(neutral,targets)

    def test_transition_movement_remains_bounded_and_updates_workload(self):
        match = self.make_match()
        match.set_possession('a','a-7',location=Location(.5,.5))
        original = {**match.player_locations('h'),**match.player_locations('a')}
        match._action_elapsed_seconds = 1
        match._update_defensive_positions(match._active_team('a'),match._active_team('h'))
        for team in ('h','a'):
            for pid,point in match.player_locations(team).items():
                distance = match.pitch.distance(original[pid],point)
                self.assertLessEqual(distance,4.000001)
                self.assertAlmostEqual(match.condition(team,pid).distance_covered,distance)

    def test_validation(self):
        for key,values in {'enabled':(1,None), 'duration_seconds':(0,-1,True,1.5),
                           'forward_distance':(-1,True,float('nan')),
                           'recovery_weight':(-1,2,True,float('inf'))}.items():
            for value in values:
                with self.assertRaises(ValueError):
                    replace(TransitionConfig(),**{key:value})
        with self.assertRaises(ValueError):
            self.make_match(transition_config={})
