from fm95.match.mechanics.offside import OffsideConfig
from dataclasses import replace
import unittest

from fm95.match.mechanics.actions import ActionConfig, shot_probabilities
from fm95.players.attributes import Attributes
from fm95.match.simulation import run_match, run_batch
from fm95.match.mechanics.boundaries import Boundary, BoundaryExit, OutOfPlayConfig
from fm95.match.mechanics.crossing import CrossConfig, can_cross, delivery_chance, aerial_chance
from fm95.match.mechanics.defending import DefenseConfig
from fm95.players.demo import demo_team
from fm95.match import Match
from fm95.match.spatial.pitch import Direction, Location, Zone
from fm95.match.mechanics.shooting import ShotConfig
from fm95.match.mechanics.goalkeeping import KeeperCrossConfig


class CrossingTests(unittest.TestCase):
    def make_match(self, delivery=1, aerial=1):
        return Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95, offside_config=OffsideConfig(enabled=False),
            keeper_cross_config=KeeperCrossConfig(enabled=False),
            action_config=ActionConfig(interval_seconds=1, on_target_probability=1,
                                      goal_given_on_target_probability=1),
            defense_config=DefenseConfig(enabled=False), shot_config=ShotConfig(enabled=False),
            out_config=OutOfPlayConfig(enabled=False),
            cross_config=CrossConfig(choice_probability=1, corner_cross_probability=1,
                                     delivery_probability=delivery, attacking_header_probability=aerial))

    def start_wide(self, match):
        match.start()
        match.set_possession("h", "h-11", location=Location(.8, .9))

    def test_crossing_zones_and_direction(self):
        for column in range(3):
            for lane in range(3):
                point = Location.centre_of(Zone(column, lane))
                self.assertEqual(can_cross(point, Direction.RIGHT), column == 2 and lane != 1)
                self.assertEqual(can_cross(point.rotated(), Direction.LEFT), column == 2 and lane != 1)

    def test_delivery_and_aerial_attribute_effects(self):
        config = CrossConfig()
        neutral = delivery_chance(.5, 0, 1, .4, config)
        self.assertGreater(delivery_chance(.9, 0, 1, .4, config), neutral)
        self.assertLess(delivery_chance(.5, 1, 1, .4, config), neutral)
        self.assertEqual(delivery_chance(.9, 0, 0, .4, config), neutral)
        self.assertGreater(aerial_chance(.9, .5, 1, config), aerial_chance(.5, .5, 1, config))
        self.assertLess(aerial_chance(.5, .9, 1, config), aerial_chance(.5, .5, 1, config))

    def test_delivered_cross_waits_for_aerial_contest_then_header_can_score(self):
        match = self.make_match()
        self.start_wide(match)
        match.step()
        self.assertEqual([e.kind for e in match.events[-2:]], ["cross_delivered", "ball_loose"])
        self.assertEqual(match.loose_ball.kind, "aerial")
        self.assertIsNone(match.possession)
        match.step()
        aerial = next(e for e in match.events if e.kind == "aerial_won")
        goal = next(e for e in match.events if e.kind == "goal")
        self.assertEqual(aerial.team_id, "h")
        self.assertNotIn(aerial.player_id, ("h-11", "h-1"))
        self.assertEqual((goal.player_id, goal.shot_type), (aerial.player_id, "header"))
        self.assertEqual(match.home_goals, 1)
        self.assertEqual((match.statistics("h").headed_shots, match.statistics("h").headed_goals), (1, 1))
        self.assertEqual(match.loose_ball_seconds, 1)
        self.assertEqual(match.statistics("h").passes_attempted, 0)

    def test_defensive_header_clears_to_ground_recovery(self):
        match = self.make_match(aerial=0)
        self.start_wide(match)
        match.step()
        match.step()
        aerial = next(e for e in match.events if e.kind == "aerial_won")
        self.assertEqual(aerial.team_id, "a")
        self.assertNotEqual(aerial.player_id, "a-1")
        self.assertEqual([e.kind for e in match.events[-2:]], ["headed_clearance", "ball_loose"])
        self.assertEqual(match.loose_ball.kind, "ground")
        self.assertEqual(match.loose_ball.last_team_id, "a")
        self.assertEqual(match.statistics("a").headed_clearances, 1)
        self.assertEqual(match.statistics("h").headed_shots, 0)

    def test_failed_delivery_is_ground_ball_or_boundary_restart(self):
        match = self.make_match(delivery=0)
        self.start_wide(match)
        match.step()
        self.assertEqual([e.kind for e in match.events[-2:]], ["cross_loose", "ball_loose"])
        self.assertEqual(match.loose_ball.kind, "ground")
        self.assertEqual(match.statistics("h").crosses_delivered, 0)
        match = self.make_match(delivery=0)
        match.out_config = OutOfPlayConfig()
        match.cross_config = replace(match.cross_config, failed_cross_out_probability=1)
        self.start_wide(match)
        match.step()
        self.assertEqual(match.events[-3].kind, "cross_out")
        self.assertIsNotNone(match.pending_restart)
        self.assertIsNone(match.loose_ball)

    def test_corner_can_deliver_cross_instead_of_short_pass(self):
        match = self.make_match()
        match.start()
        match.award_out_of_play(BoundaryExit(Boundary.RIGHT, Location(1, .8)), "a", "a-3")
        match.step()
        self.assertEqual([e.kind for e in match.events[-3:]],
                         ["corner_taken", "cross_delivered", "ball_loose"])
        self.assertEqual(match.statistics("h").corners_taken, 1)
        self.assertEqual(match.statistics("h").crosses_attempted, 1)
        self.assertEqual(match.statistics("h").passes_attempted, 0)

    def test_dismissed_players_and_crosser_cannot_contest(self):
        match = self.make_match()
        self.start_wide(match)
        match.step()
        match.issue_card("h", "h-9", "red")
        match.issue_card("a", "a-3", "red")
        match.step()
        event = next(e for e in match.events if e.kind == "aerial_won")
        self.assertNotIn(event.player_id, ("h-9", "a-3", "h-11", "h-1", "a-1"))
        self.assertNotIn(event.opponent_player_id, ("h-9", "a-3", "h-11", "h-1", "a-1"))

    def test_heading_accuracy_and_finishing_have_separate_roles(self):
        config, zone = ActionConfig(), Zone(2, 1)
        weak = shot_probabilities(zone, config, heading=.1)
        strong = shot_probabilities(zone, config, heading=.9)
        self.assertGreater(strong[0], weak[0])
        self.assertEqual(strong[1], weak[1])
        finishing = shot_probabilities(zone, config, finishing=.9, heading=.9)
        self.assertEqual(finishing[0], strong[0])
        self.assertGreater(finishing[1], strong[1])

    def test_seeded_full_match_and_batch_stats_reconcile(self):
        matches = [run_match(Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95)) for _ in range(2)]
        self.assertEqual(matches[0].events, matches[1].events)
        match = matches[0]
        home, away = match.statistics("h"), match.statistics("a")
        contests = sum(e.kind == "aerial_won" for e in match.events)
        self.assertGreater(contests, 0)
        self.assertEqual(home.aerials_won+away.aerials_won, contests)
        self.assertEqual(home.aerials_attempted, away.aerials_attempted)
        for stats in (home, away):
            self.assertLessEqual(stats.headed_shots, stats.aerials_won)
            self.assertLessEqual(stats.crosses_delivered, stats.crosses_attempted)
        self.assertEqual(home.possession_seconds+away.possession_seconds+match.loose_ball_seconds+match.dead_ball_seconds, 5400)
        summary = run_batch(1, cross_config=CrossConfig(enabled=False))
        self.assertFalse(summary["crossing_configuration"]["enabled"])
        self.assertEqual(summary["team_averages"]["home"]["crosses_attempted"], 0)
        self.assertEqual(summary["team_averages"]["away"]["headed_shots"], 0)

    def test_validation_and_invalid_aerial_override_is_atomic(self):
        for name in ("crossing", "heading"):
            for value in (-1, float("nan"), True):
                with self.assertRaises(ValueError):
                    Attributes(**{name: value})
        for values in ({"choice_probability":1.1}, {"delivery_probability":-.1},
                       {"attacking_header_probability":float("nan")}, {"clearance_distance":-1}):
            with self.assertRaises(ValueError):
                CrossConfig(**values)
        match = self.make_match()
        self.start_wide(match)
        match.set_loose_ball(Location(.9, .5))
        original = match.loose_ball
        with self.assertRaises(ValueError):
            match.set_loose_ball(Location(.9, .5), aerial=True)
        self.assertEqual(match.loose_ball, original)
