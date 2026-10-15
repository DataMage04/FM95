from dataclasses import replace
import unittest

from fm95.actions import ActionConfig
from fm95.batch import run_match, run_batch
from fm95.defending import DefenseConfig
from fm95.demo import demo_team
from fm95.match import Match, Phase
from fm95.pitch import Location
from fm95.recovery import RecoveryConfig


class RecoveryTests(unittest.TestCase):
    def make_match(self, config=None, recovery=None, defense=None):
        return Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95,
            action_config=config or ActionConfig(interval_seconds=1, shot_probability=0,
                dribble_probability=0, completion_probability=0, foul_probability=0),
            recovery_config=recovery or RecoveryConfig(misplaced_pass_probability=1),
            defense_config=defense or DefenseConfig(enabled=False))

    def test_failed_pass_creates_unowned_ball_and_recovery_consumes_action(self):
        match = self.make_match(recovery=RecoveryConfig(misplaced_pass_probability=1, movement_speed=200))
        match.start()
        match.step()
        self.assertEqual([e.kind for e in match.events[-2:]], ["pass_loose", "ball_loose"])
        self.assertIsNone(match.possession)
        self.assertEqual(match.ball_location, match.loose_ball.location)
        self.assertEqual(match.loose_ball.last_team_id, "h")
        self.assertIsNone(match.events[-2].interceptor_id)
        index = len(match.events)
        point = match.ball_location
        match.step()
        self.assertEqual([e.kind for e in match.events[index:]], ["ball_recovered"])
        self.assertIsNone(match.loose_ball)
        self.assertEqual(match.possession.location, point)
        self.assertEqual(match.loose_ball_seconds, 1)
        winner = match.events[-1].team_id
        self.assertEqual(match.statistics(winner).recoveries, 1)

    def test_unreachable_ball_stays_uncontrolled(self):
        match = self.make_match(recovery=RecoveryConfig(movement_speed=0, control_radius=0))
        match.start()
        point = Location(.01, .01)
        match.set_loose_ball(point)
        match.step()
        self.assertIsNone(match.possession)
        self.assertEqual(match.ball_location, point)
        self.assertEqual(match.events[-1].kind, "ball_unrecovered")
        self.assertEqual(match.events[-1].recovery_candidates, 0)
        self.assertEqual(match.loose_ball_seconds, 1)
        self.assertEqual(match.pressure_on_ball().intensity, 0)

    def test_only_nearby_active_players_can_recover(self):
        match = self.make_match(recovery=RecoveryConfig(movement_speed=0, control_radius=.1))
        match.start()
        point = match.player_locations("h")["h-11"]
        match.set_loose_ball(point)
        match.step()
        self.assertEqual(match.possession.player_id, "h-11")
        match.issue_card("h", "h-11", "red")
        match.set_possession("h", "h-2", location=Location(.1, .01))
        match.set_loose_ball(point)
        match.step()
        self.assertIsNone(match.possession)

    def test_goalkeeper_can_recover_only_in_own_penalty_area(self):
        match = self.make_match(recovery=RecoveryConfig(movement_speed=0, control_radius=.1))
        match.start()
        point = match.player_locations("h")["h-1"]
        match.set_loose_ball(point)
        match.step()
        self.assertEqual(match.possession.player_id, "h-1")
        # Move keeper to an outfield location via development possession, then release it.
        outside = Location(.45, .01)
        match.set_possession("h", "h-1", location=outside)
        match.set_loose_ball(outside)
        match.step()
        self.assertIsNone(match.possession)

    def test_tackle_can_dispossess_without_gaining_control(self):
        action = ActionConfig(interval_seconds=1, shot_probability=0, dribble_probability=1,
                              dribble_success_probability=0, foul_probability=0)
        match = self.make_match(action, RecoveryConfig(tackle_loose_probability=1))
        match.start()
        original = match.ball_location
        match.step()
        self.assertEqual([e.kind for e in match.events[-2:]], ["dribble_dispossessed", "ball_loose"])
        self.assertEqual(match.ball_location, original)
        self.assertIsNone(match.possession)
        self.assertEqual(match.statistics("a").tackles_won, 1)
        self.assertEqual(match.statistics("a").recoveries, 0)

    def test_press_can_knock_ball_loose(self):
        match = self.make_match(recovery=RecoveryConfig(tackle_loose_probability=1),
            defense=DefenseConfig(movement_speed=200, press_attempt_probability=1, press_win_probability=1))
        match.start()
        match.step()
        self.assertEqual([e.kind for e in match.events[-2:]], ["press_dispossessed", "ball_loose"])
        self.assertIsNone(match.possession)
        self.assertEqual(match.statistics("a").presses_won, 1)

    def test_period_end_and_overrides_clear_loose_state(self):
        match = self.make_match(config=ActionConfig(interval_seconds=9999))
        match.start()
        match.set_loose_ball(Location(.01, .01))
        for _ in range(2700):
            match.step()
        self.assertEqual(match.phase, Phase.HALF_TIME)
        self.assertIsNone(match.loose_ball)
        self.assertIsNone(match.ball_location)
        self.assertEqual(match.loose_ball_seconds, 2700)
        match.resume()
        self.assertIsNotNone(match.possession)
        match.set_loose_ball(Location(.1, .1))
        match.set_possession("a", "a-2", location=Location(.2, .2))
        self.assertIsNone(match.loose_ball)
        match.set_loose_ball(Location(.1, .1))
        for player in ("h-2", "h-3", "h-4", "h-5", "h-6"):
            match.issue_card("h", player, "red")
        self.assertEqual(match.phase, Phase.ABANDONED)
        self.assertIsNone(match.loose_ball)

    def test_reproducibility_time_and_batch_reconciliation(self):
        matches = [run_match(Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95))
                   for _ in range(2)]
        self.assertEqual(matches[0].events, matches[1].events)
        match = matches[0]
        home, away = match.statistics("h"), match.statistics("a")
        self.assertGreater(match.loose_ball_seconds, 0)
        self.assertEqual(home.possession_seconds+away.possession_seconds+match.loose_ball_seconds, 5400)
        self.assertAlmostEqual(home.possession_percentage+away.possession_percentage, 100)
        for own, other in ((home, away), (away, home)):
            self.assertEqual(own.passes_attempted-own.passes_completed,
                             other.interceptions+own.misplaced_passes)
            self.assertEqual(own.recoveries, sum(e.kind == "ball_recovered" and e.team_id == own.team_id
                                                for e in match.events))
        summary = run_batch(1)
        self.assertAlmostEqual(sum(s["possession_seconds"] for s in summary["team_averages"].values())
                               + summary["average_loose_ball_seconds"], 5400)

    def test_disabled_outcomes_and_configuration_validation(self):
        match = self.make_match(recovery=RecoveryConfig(enabled=False))
        match.start()
        match.step()
        self.assertEqual(match.events[-1].kind, "pass_intercepted")
        self.assertIsNone(match.loose_ball)
        for values in ({"movement_speed":-1}, {"control_radius":float("nan")},
                       {"misplaced_pass_probability":1.1}, {"tackle_loose_probability":-.1}):
            with self.assertRaises(ValueError):
                RecoveryConfig(**values)
        with self.assertRaises(RuntimeError):
            self.make_match().set_loose_ball(Location(.5, .5))
