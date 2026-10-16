from fm95.offside import OffsideConfig
from dataclasses import replace
import unittest

from fm95.actions import ActionConfig
from fm95.attributes import Attributes
from fm95.batch import run_match, run_batch
from fm95.boundaries import OutOfPlayConfig
from fm95.crossing import CrossConfig
from fm95.defending import DefenseConfig
from fm95.demo import demo_team
from fm95.goalkeeping import KeeperCrossConfig, handling_chance, keeper_can_intervene
from fm95.match import Match
from fm95.pitch import Direction, Location, Pitch
from fm95.recovery import RecoveryConfig
from fm95.shooting import ShotConfig


class KeeperCrossTests(unittest.TestCase):
    def make_match(self, success=1, claim=1, handling=.5):
        return Match(demo_team("h", "Home"), demo_team("a", "Away", attributes=Attributes(handling=handling)),
            seed=95, offside_config=OffsideConfig(enabled=False), action_config=ActionConfig(interval_seconds=1, shot_probability=0,
                dribble_probability=0, on_target_probability=1, goal_given_on_target_probability=1),
            defense_config=DefenseConfig(enabled=False), recovery_config=RecoveryConfig(enabled=False),
            out_config=OutOfPlayConfig(enabled=False), shot_config=ShotConfig(enabled=False),
            cross_config=CrossConfig(attacking_header_probability=1),
            keeper_cross_config=KeeperCrossConfig(attempt_probability=1, success_probability=success,
                claim_probability=claim, movement_speed=200, intervention_radius=200))

    def deliver(self, match, point=Location(.9, .5)):
        match.start()
        match.set_possession("h", "h-11", location=Location(.8, .9))
        match.set_loose_ball(point, aerial=True, reason="cross_delivery")

    def test_claim_consumes_action_and_gives_keeper_control_without_save(self):
        match = self.make_match()
        self.deliver(match)
        index = len(match.events)
        match.step()
        self.assertEqual([e.kind for e in match.events[index:]], ["keeper_cross_claimed"])
        self.assertEqual((match.possession.team_id, match.possession.player_id), ("a", "a-1"))
        self.assertEqual(match.ball_location, Location(.9, .5))
        self.assertIsNone(match.loose_ball)
        stats = match.statistics("a")
        self.assertEqual((stats.keeper_cross_attempts, stats.crosses_claimed, stats.saves), (1, 1, 0))
        self.assertEqual(match.statistics("h").headed_shots, 0)
        match.step()
        self.assertTrue(match.events[-1].kind.startswith("pass_"))

    def test_punch_creates_ground_recovery_without_shot_or_save(self):
        match = self.make_match(claim=0)
        self.deliver(match)
        match.step()
        self.assertEqual([e.kind for e in match.events[-2:]], ["keeper_cross_punched", "ball_loose"])
        self.assertIsNone(match.possession)
        self.assertEqual((match.loose_ball.kind, match.loose_ball.reason, match.loose_ball.last_player_id),
                         ("ground", "goalkeeper_punch", "a-1"))
        self.assertEqual(match.statistics("a").crosses_punched, 1)
        self.assertEqual(match.statistics("a").saves, 0)
        self.assertEqual(match.statistics("h").shots, 0)

    def test_failed_intervention_allows_outfield_header(self):
        match = self.make_match(success=0)
        self.deliver(match)
        match.step()
        kinds = [e.kind for e in match.events]
        self.assertLess(kinds.index("keeper_cross_missed"), kinds.index("aerial_won"))
        self.assertEqual(match.statistics("a").keeper_cross_failures, 1)
        self.assertEqual(match.statistics("h").headed_shots, 1)
        self.assertEqual(match.home_goals, 1)

    def test_area_and_movement_gate_for_both_ends(self):
        pitch, config = Pitch(), KeeperCrossConfig(attempt_probability=1)
        keeper, ball = Location(.95, .5), Location(.9, .5)
        self.assertTrue(keeper_can_intervene(keeper, ball, Direction.LEFT, pitch, 6, config))
        self.assertTrue(keeper_can_intervene(keeper.rotated(), ball.rotated(), Direction.RIGHT, pitch, 6, config))
        self.assertFalse(keeper_can_intervene(keeper, Location(.8, .5), Direction.LEFT, pitch, 6, config))
        self.assertFalse(keeper_can_intervene(keeper, ball, Direction.LEFT, pitch, 1,
                                            replace(config, movement_speed=0, contact_radius=0)))
        match = self.make_match()
        self.deliver(match, Location(.8, .5))
        match.step()
        self.assertFalse(any(e.kind.startswith("keeper_cross_") for e in match.events))

    def test_handling_changes_intervention_probabilities_and_is_recorded(self):
        self.assertGreater(handling_chance(.7, .9, 1), handling_chance(.7, .5, 1))
        self.assertEqual(handling_chance(.7, .9, 0), .7)
        for endpoint in (0, 1):
            self.assertEqual(handling_chance(endpoint, .9, 1), endpoint)
        match = self.make_match(success=.7, claim=.6, handling=.9)
        self.deliver(match)
        match.step()
        event = next(e for e in match.events if e.kind.startswith("keeper_cross_"))
        self.assertEqual(event.goalkeeper_handling, .9)
        self.assertGreater(event.keeper_success_probability, .7)
        self.assertGreater(event.keeper_claim_probability, .6)

    def test_handling_changes_parries_without_changing_original_scoring_chance(self):
        shots = []
        for handling in (.1, .9):
            match = self.make_match(handling=handling)
            match.action_config = replace(match.action_config, shot_probability=1,
                                           goal_given_on_target_probability=0)
            match.shot_config = ShotConfig(block_probability=0, parry_probability=.5)
            match.start()
            match.set_possession("h", "h-9", location=Location(.8, .5))
            match.step()
            shots.append(next(e for e in match.events if e.goal_probability is not None))
        self.assertGreater(shots[0].parry_probability, shots[1].parry_probability)
        self.assertEqual(shots[0].goal_probability, shots[1].goal_probability)
        self.assertEqual(shots[0].on_target_probability, shots[1].on_target_probability)

    def test_emergency_keeper_is_used_and_dismissed_keeper_is_excluded(self):
        match = self.make_match()
        self.deliver(match)
        match.issue_card("a", "a-1", "red")
        match.step()
        event = next(e for e in match.events if e.kind.startswith("keeper_cross_"))
        self.assertEqual(event.player_id, "a-2")
        self.assertEqual(match.possession.player_id, "a-2")

    def test_punch_out_records_keeper_last_touch(self):
        match = self.make_match(claim=0)
        match.out_config = OutOfPlayConfig()
        match.keeper_cross_config = replace(match.keeper_cross_config, punch_distance=1000)
        self.deliver(match)
        match.step()
        out = next(e for e in match.events if e.kind == "ball_out")
        self.assertEqual((out.team_id, out.player_id), ("a", "a-1"))
        self.assertIsNotNone(match.pending_restart)
        self.assertIsNone(match.loose_ball)

    def test_full_match_and_batch_reproduce_and_reconcile(self):
        matches = [run_match(Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95)) for _ in range(2)]
        self.assertEqual(matches[0].events, matches[1].events)
        match = matches[0]
        for team in ("h", "a"):
            stats = match.statistics(team)
            self.assertEqual(stats.keeper_cross_attempts,
                             stats.crosses_claimed+stats.crosses_punched+stats.keeper_cross_failures)
            self.assertEqual(stats.crosses_claimed, sum(e.kind == "keeper_cross_claimed" and e.team_id == team
                                                       for e in match.events))
        home, away = match.statistics("h"), match.statistics("a")
        self.assertEqual(home.possession_seconds+away.possession_seconds+match.loose_ball_seconds+match.dead_ball_seconds, 5400)
        summary = run_batch(1, keeper_cross_config=KeeperCrossConfig(enabled=False))
        self.assertFalse(summary["keeper_crossing_configuration"]["enabled"])
        self.assertEqual(summary["team_averages"]["home"]["keeper_cross_attempts"], 0)

    def test_configuration_and_attribute_validation(self):
        for values in ({"attempt_probability":1.1}, {"success_probability":-.1},
                       {"claim_probability":float("nan")}, {"movement_speed":-1},
                       {"intervention_radius":float("inf")}, {"enabled":1}):
            with self.assertRaises(ValueError):
                KeeperCrossConfig(**values)
        for handling in (-1, 1.1, float("nan"), True):
            with self.assertRaises(ValueError):
                Attributes(handling=handling)
