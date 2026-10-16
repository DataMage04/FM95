from dataclasses import FrozenInstanceError, asdict, replace
import unittest
from unittest.mock import patch

from fm95.match.mechanics.defending import Pressure
from fm95.match.mechanics.shooting import ShotConfig
from fm95.match.mechanics.actions import ActionConfig
from fm95.match.simulation import run_batch, run_match
from fm95.players.demo import demo_team
from fm95.match import Match, Phase, Restart
from fm95.match.spatial.pitch import Location
from fm95.match.systems.timekeeping import AddedTimeConfig


class AddedTimeTests(unittest.TestCase):
    def make_match(self, enabled=True, **settings):
        match=Match(demo_team('h','Home',include_bench=True),demo_team('a','Away',include_bench=True),seed=95,
            action_config=ActionConfig(interval_seconds=99999,foul_probability=0),
            added_time_config=AddedTimeConfig(enabled=enabled,rounding_seconds=1,**settings))
        match.start()
        return match

    def advance_to(self, match, target):
        while match.elapsed_seconds<target:
            match.step()

    def test_consumed_delay_extends_only_its_half_and_reconciles_time(self):
        match=self.make_match()
        match.delay_play(3,reason='test_stoppage')
        self.assertEqual(match.elapsed_seconds,0)
        for _ in range(3):match.step()
        self.assertEqual(match.period_timing.time_lost_seconds,3)
        self.advance_to(match,2700)
        self.assertEqual(match.phase,Phase.FIRST_HALF)
        self.assertEqual(match.period_timing.minimum_added_seconds,3)
        self.advance_to(match,2703)
        self.assertEqual(match.phase,Phase.HALF_TIME)
        match.resume()
        self.assertEqual(match.period_timing.period_elapsed_seconds,0)
        self.assertEqual(match.period_timing.time_lost_seconds,0)
        self.assertEqual(match.period_timing.target_end_seconds,5403)
        self.advance_to(match,5403)
        self.assertEqual(match.phase,Phase.FULL_TIME)
        accounted=sum(match.statistics(t).possession_seconds for t in ('h','a'))+match.loose_ball_seconds+match.dead_ball_seconds
        self.assertEqual(accounted,5403)

    def test_delays_in_added_time_extend_announced_minimum(self):
        match=self.make_match()
        match.delay_play(2,reason='initial')
        self.advance_to(match,2700)
        self.assertEqual(match.period_timing.minimum_added_seconds,2)
        match.delay_play(3,reason='added_time_stoppage')
        self.advance_to(match,2703)
        self.assertEqual(match.period_timing.minimum_added_seconds,2)
        self.assertEqual(match.period_timing.target_end_seconds,2705)
        self.advance_to(match,2705)
        self.assertEqual(match.phase,Phase.HALF_TIME)
        announced=[e for e in match.events if e.kind=='added_time_announced']
        self.assertEqual(len(announced),1)
        self.assertEqual(announced[0].added_seconds,2)

    def test_overlapping_delays_share_seconds_and_do_not_advance_actions(self):
        match=self.make_match()
        match.delay_play(4,reason='injury')
        match.delay_play(2,reason='substitution_overlap')
        with patch.object(match,'_play_action') as play:
            for _ in range(4):match.step()
        play.assert_not_called()
        self.assertEqual(match.period_timing.time_lost_seconds,4)
        self.assertEqual(match.period_timing.restart_delay_seconds,0)
        self.assertEqual(match._seconds_since_action,0)

    def test_substitutions_queue_one_delay_and_halftime_changes_do_not(self):
        match=self.make_match(substitution_seconds=3)
        match.substitute_many('h',(('h-7','h-15'),('h-9','h-18')))
        match.step()
        self.assertEqual(match.period_timing.restart_delay_seconds,2)
        self.assertEqual(match.period_timing.time_lost_seconds,1)
        self.advance_to(match,2703)
        match.substitute('a','a-7','a-15')
        match.resume()
        match.step()
        self.assertEqual(match.period_timing.restart_delay_seconds,0)
        self.assertEqual(match.period_timing.time_lost_seconds,0)

    def test_pending_penalty_resolves_at_shifted_whistle_without_kickoff(self):
        match=self.make_match()
        match.delay_play(2,reason='test')
        self.advance_to(match,2701)
        ball=Location(1-11/match.pitch.length,.5)
        match._possession=None
        match._pending_restart=Restart('penalty','h','h-9',ball.zone,ball)
        match.set_piece_config=replace(match.set_piece_config,penalty_on_target_probability=1,
                                      penalty_goal_given_on_target_probability=1)
        match.step()
        self.assertEqual(match.phase,Phase.HALF_TIME)
        self.assertEqual(match.home_goals,1)
        self.assertFalse(any(e.kind=='kickoff' and e.elapsed_seconds==2702 for e in match.events))
        self.assertEqual(match.events[-1].kind,'half_time')

    def test_default_rounding_is_minimum_and_can_be_increased(self):
        match=self.make_match()
        match.added_time_config=AddedTimeConfig(enabled=True)
        match.delay_play(1,reason='test')
        self.advance_to(match,2700)
        self.assertEqual(match.period_timing.minimum_added_seconds,60)
        self.assertEqual(match.period_timing.target_end_seconds,2760)
        match.delay_play(2,reason='further')
        match.step();match.step()
        self.assertEqual(match.period_timing.target_end_seconds,2762)
        with self.assertRaises(FrozenInstanceError):
            match.period_timing.minimum_added_seconds=0

    def test_disabled_is_neutral_and_invalid_requests_are_atomic(self):
        match=self.make_match(enabled=False)
        with self.assertRaises(RuntimeError):match.delay_play(1,reason='test')
        self.advance_to(match,2700)
        self.assertEqual(match.phase,Phase.HALF_TIME)
        self.assertFalse(any(e.kind=='added_time_announced' for e in match.events))
        match=self.make_match()
        before=tuple(match.events)
        for seconds,reason in ((-1,'x'),(True,'x'),(1,''),(1,None)):
            with self.assertRaises(ValueError):match.delay_play(seconds,reason=reason)
        self.assertEqual(tuple(match.events),before)
        match.set_possession('h','h-7',location=Location(.5,.5))
        with self.assertRaises(RuntimeError):match.delay_play(1,reason='open_play')
        for field in ('substitution_seconds','injury_seconds','goal_seconds','discipline_seconds'):
            for value in (-1,True,1.5):
                with self.assertRaises(ValueError):AddedTimeConfig(**{field:value})
        for value in (0,True,-1):
            with self.assertRaises(ValueError):AddedTimeConfig(rounding_seconds=value)
        with self.assertRaises(ValueError):AddedTimeConfig(enabled=1)

    def test_automatic_goal_delay_is_dead_time_and_injury_discipline_overlap(self):
        match=self.make_match(goal_seconds=3,injury_seconds=4,discipline_seconds=2)
        match.action_config=replace(match.action_config,on_target_probability=1,goal_given_on_target_probability=1)
        match.shot_config=ShotConfig(enabled=False)
        match.set_possession('h','h-9',location=Location(.8,.5))
        match._play_shot(match.possession,match._active_team('h'),match._active_team('a'),Pressure(None,None,0))
        match.step()
        self.assertEqual(match.period_timing.restart_delay_seconds,2)
        self.assertEqual(match.dead_ball_seconds,1)
        self.assertEqual(match.statistics('h').possession_seconds+match.statistics('a').possession_seconds,0)
        match.issue_card('h','h-7','yellow')
        match.injure_player('h','h-8')
        match.step()
        self.assertEqual(match.period_timing.restart_delay_seconds,3)
        self.assertEqual(match.period_timing.time_lost_seconds,2)

    def test_second_half_uses_shifted_start_and_penalty_ends_at_new_deadline(self):
        match=self.make_match()
        match.delay_play(2,reason='first_half')
        self.advance_to(match,2702)
        match.resume()
        match.delay_play(3,reason='second_half')
        self.advance_to(match,5404)
        self.assertEqual(match.phase,Phase.SECOND_HALF)
        self.assertEqual(match.period_timing.minimum_added_seconds,3)
        self.assertEqual(match.period_timing.target_end_seconds,5405)
        ball=Location(11/match.pitch.length,.5)
        match._possession=None
        match._pending_restart=Restart('penalty','h','h-9',ball.zone,ball)
        match.set_piece_config=replace(match.set_piece_config,penalty_on_target_probability=1,
                                      penalty_goal_given_on_target_probability=1)
        match.step()
        self.assertEqual(match.phase,Phase.FULL_TIME)
        self.assertEqual(match.home_goals,1)
        self.assertFalse(any(e.kind=='kickoff' and e.elapsed_seconds==5405 for e in match.events))

    def test_development_override_cancels_remaining_delay_without_losing_consumed_time(self):
        match=self.make_match()
        match.delay_play(5,reason='test')
        match.step()
        match.set_possession('h','h-7',location=Location(.5,.5))
        self.assertEqual(match.period_timing.restart_delay_seconds,0)
        self.assertEqual(match.period_timing.time_lost_seconds,1)
        with self.assertRaises(ValueError):
            Match(demo_team('h','Home'),demo_team('a','Away'),added_time_config={})
