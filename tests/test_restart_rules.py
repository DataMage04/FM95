from dataclasses import FrozenInstanceError
import unittest
from unittest.mock import patch

from fm95.match.mechanics.actions import ActionConfig
from fm95.match.mechanics.boundaries import Boundary, BoundaryExit, OutOfPlayConfig
from fm95.match.mechanics.crossing import CrossConfig
from fm95.match.mechanics.defending import DefenseConfig, Pressure
from fm95.players.demo import demo_team
from fm95.match import Match, Phase, Restart
from fm95.match.spatial.pitch import Location
from fm95.match.mechanics.recovery import RecoveryConfig
from fm95.match.mechanics.restart_rules import RestartContext, indirect_location
from fm95.match.mechanics.shooting import ShotConfig


class RestartRuleTests(unittest.TestCase):
    def make_match(self):
        match = Match(demo_team('h','Home'),demo_team('a','Away'),seed=95,
            defense_config=DefenseConfig(enabled=False),cross_config=CrossConfig(enabled=False),
            action_config=ActionConfig(foul_probability=0,completion_probability=1))
        match.start()
        match.set_possession('h','h-7',location=Location(.5,.5))
        return match

    def delivery(self, match, kind, team='h', taker='h-7'):
        match._restart_context = RestartContext(kind,team,taker)

    def test_direct_goal_matrix_at_both_ends(self):
        for kind in ('kickoff','free_kick','indirect_free_kick','corner','goal_kick','throw_in','dropped_ball'):
            for own_goal in (False,True):
                match = self.make_match()
                self.delivery(match,kind)
                x = 0 if own_goal else 1
                match.resolve_restart_exit(BoundaryExit(Boundary.LEFT if own_goal else Boundary.RIGHT,Location(x,.5)))
                allowed = not own_goal and kind not in ('indirect_free_kick','throw_in','dropped_ball')
                if allowed:
                    self.assertEqual(match.home_goals,1)
                    self.assertEqual(match.possession.team_id,'a')
                else:
                    self.assertEqual((match.home_goals,match.away_goals),(0,0))
                    self.assertEqual(match.pending_restart.kind,'corner' if own_goal else 'goal_kick')
                    self.assertEqual(match.pending_restart.team_id,'a')
                self.assertIsNone(match.restart_context)

    def test_second_touch_awards_indirect_kick_and_other_player_releases_restriction(self):
        for kind in ('kickoff','free_kick','indirect_free_kick','corner','goal_kick','throw_in','penalty'):
            match = self.make_match()
            self.delivery(match,kind)
            self.assertFalse(match.record_ball_touch('h','h-7',Location(.4,.5)))
            self.assertEqual(match.pending_restart.kind,'indirect_free_kick')
            self.assertEqual(match.events[-2].kind,'restart_second_touch')
            self.assertEqual(match.events[-2].reason,kind)
            self.assertEqual(match.statistics('a').indirect_free_kicks_awarded,1)
            self.assertIsNone(match.possession)
            match = self.make_match()
            self.delivery(match,kind)
            self.assertTrue(match.record_ball_touch('a','a-7',Location(.4,.5)))
            self.assertIsNone(match.restart_context)
            self.assertTrue(match.record_ball_touch('h','h-7',Location(.4,.5)))

    def test_dropped_ball_repeated_recipient_touches_do_not_satisfy_two_player_rule(self):
        match = self.make_match()
        self.delivery(match,'dropped_ball')
        for _ in range(3):
            self.assertTrue(match.record_ball_touch('h','h-7',Location(.5,.5)))
        self.assertIsNotNone(match.restart_context)
        match.record_ball_touch('h','h-8',Location(.5,.5))
        self.assertIsNone(match.restart_context)
        match.resolve_deflection_exit(BoundaryExit(Boundary.RIGHT,Location(1,.5)),'h','h-8')
        self.assertEqual(match.home_goals,1)

    def test_engine_restart_pass_touches_receiver_and_clears_context(self):
        match = self.make_match()
        point = Location(.5,0)
        match._possession = None
        match._pending_restart = Restart('throw_in','h','h-7',point.zone,point)
        match._play_action()
        self.assertTrue(any(e.kind=='throw_in_taken' for e in match.events))
        self.assertIsNone(match.restart_context)
        self.assertNotEqual(match.possession.player_id,'h-7')

    def test_engine_loose_ball_taker_recovery_is_a_second_touch(self):
        match = self.make_match()
        self.delivery(match,'throw_in')
        match.set_loose_ball(Location(.5,.5))
        with patch.object(match._rng,'choices',return_value=[('h',match.active_players('h')[6])]):
            match._play_action()
        self.assertEqual(match.pending_restart.kind,'indirect_free_kick')
        self.assertIsNone(match.loose_ball)

    def test_keeper_deflection_releases_indirect_scoring_restriction(self):
        match = self.make_match()
        self.delivery(match,'indirect_free_kick')
        match.resolve_deflection_exit(BoundaryExit(Boundary.RIGHT,Location(1,.5)),'a','a-1')
        self.assertEqual(match.home_goals,1)
        self.assertEqual(match.statistics('a').own_goals,1)

    def test_goal_area_placement_and_touch_validation(self):
        match = self.make_match()
        self.delivery(match,'goal_kick',taker='h-1')
        self.assertFalse(match.record_ball_touch('h','h-1',Location(.01,.5)))
        self.assertAlmostEqual(match.pending_restart.location.x*match.pitch.length,5.5)
        match = self.make_match()
        self.delivery(match,'throw_in')
        snapshot = match.restart_context
        with self.assertRaises(FrozenInstanceError):
            snapshot.kind = 'corner'
        before = tuple(match.events)
        for team,pid,point in (('h','a-7',Location(.5,.5)),('h','h-7',None)):
            with self.assertRaises(ValueError):
                match.record_ball_touch(team,pid,point)
        self.assertEqual(tuple(match.events),before)
        self.assertEqual(match.restart_context,snapshot)

    def test_stoppages_and_development_override_clear_context(self):
        match = self.make_match()
        self.delivery(match,'throw_in')
        match.set_possession('h','h-7',location=Location(.5,.5))
        self.assertIsNone(match.restart_context)
        self.delivery(match,'corner')
        match.award_out_of_play(BoundaryExit(Boundary.TOP,Location(.5,1)),'h','h-7')
        self.assertIsNone(match._restart_context)
        with self.assertRaises(RuntimeError):
            match.resolve_restart_exit(BoundaryExit(Boundary.RIGHT,Location(1,.5)))

    def test_defender_knocking_restart_loose_releases_taker_restriction(self):
        match = self.make_match()
        self.delivery(match,'kickoff')
        match.defense_config = DefenseConfig(press_attempt_probability=1,press_win_probability=1)
        match.recovery_config = RecoveryConfig(tackle_loose_probability=1)
        stopped,attempted = match._try_press(match.possession,match._active_team('h'),
            match._active_team('a'),Pressure('a-7',0,1))
        self.assertTrue(stopped)
        self.assertIsNotNone(match.loose_ball)
        self.assertIsNone(match.restart_context)
        self.assertTrue(match.record_ball_touch('h','h-7',Location(.5,.5)))

    def test_engine_throw_in_exit_cannot_score_directly(self):
        match = self.make_match()
        match.action_config = ActionConfig(completion_probability=0)
        match.out_config = OutOfPlayConfig(failed_pass_out_probability=1)
        point = Location(.5,.5)
        match._possession = None
        match._pending_restart = Restart('throw_in','h','h-7',point.zone,point)
        with patch('fm95.match.engine.misplaced_endpoint',return_value=(1.1,.5)):
            match._play_action()
        self.assertEqual(match.home_goals,0)
        self.assertEqual(match.pending_restart.kind,'goal_kick')
        self.assertTrue(any(e.kind=='direct_restart_goal_disallowed' for e in match.events))

    def test_one_player_dropped_ball_shot_cannot_score(self):
        match = self.make_match()
        match.shot_config = ShotConfig(enabled=False)
        match.action_config = ActionConfig(on_target_probability=1,goal_given_on_target_probability=1)
        match.set_possession('h','h-9',location=Location(.8,.5))
        self.delivery(match,'dropped_ball',taker='h-9')
        match._play_shot(match.possession,match._active_team('h'),match._active_team('a'),Pressure(None,None,0))
        self.assertEqual(match.home_goals,0)
        self.assertEqual(match.pending_restart.kind,'goal_kick')
        self.assertEqual(match.statistics('h').expected_goals,0)

    def test_repeated_dropped_ball_recipient_deflection_still_needs_second_player(self):
        match = self.make_match()
        self.delivery(match,'dropped_ball')
        match.resolve_deflection_exit(BoundaryExit(Boundary.RIGHT,Location(1,.5)),'h','h-7')
        self.assertEqual(match.home_goals,0)
        self.assertEqual(match.pending_restart.kind,'goal_kick')
