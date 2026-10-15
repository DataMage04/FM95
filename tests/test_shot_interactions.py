from fm95.boundaries import OutOfPlayConfig
from dataclasses import replace
from random import Random
import unittest

from fm95.actions import ActionConfig, resolve_shot, shot_probabilities
from fm95.batch import run_match, run_batch
from fm95.defending import DefenseConfig
from fm95.demo import demo_team
from fm95.match import Match
from fm95.pitch import Direction, Location, Pitch, Zone
from fm95.shooting import ShotConfig, blocking_context, rebound_location


class ShotInteractionTests(unittest.TestCase):
    def make_match(self, config, goal=0):
        return Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95,
            out_config=OutOfPlayConfig(enabled=False),
            action_config=ActionConfig(interval_seconds=1, shot_probability=1,
                on_target_probability=1, goal_given_on_target_probability=goal),
            defense_config=DefenseConfig(enabled=False), shot_config=config)

    def test_only_outfield_players_between_shooter_and_goal_can_block(self):
        away = demo_team("a", "Away")
        players = (away.lineup[0], away.lineup[2])
        origin, pitch = Location(.7, .5), Pitch()
        config = ShotConfig(block_probability=1)
        locations = {"a-1": Location(.9, .5), "a-3": Location(.8, .5)}
        self.assertEqual(blocking_context(players, locations, origin, Direction.RIGHT, pitch, config), ("a-3", 1))
        for point in (Location(.6, .5), Location(.8, .9)):
            locations["a-3"] = point
            self.assertEqual(blocking_context(players, locations, origin, Direction.RIGHT, pitch, config), (None, 0))
        locations["a-3"] = Location(.8, .5)
        mirrored = {key: point.rotated() for key, point in locations.items()}
        self.assertEqual(blocking_context(players, mirrored, origin.rotated(), Direction.LEFT, pitch, config), ("a-3", 1))

    def test_blocked_shot_records_block_without_save_and_leaves_rebound(self):
        match = self.make_match(ShotConfig(block_probability=1, rebound_distance=4), goal=1)
        match.start()
        match.set_possession("a", "a-3", location=Location(.8, .5))
        match.set_possession("h", "h-9", location=Location(.7, .5))
        match.step()
        shot, loose = match.events[-2:]
        self.assertEqual((shot.kind, shot.blocking_player_id), ("shot_blocked", "a-3"))
        self.assertEqual(shot.block_probability, 1)
        self.assertEqual(shot.goal_probability, 0)
        self.assertEqual(loose.kind, "ball_loose")
        self.assertEqual(match.loose_ball.reason, "blocked_shot")
        self.assertIsNone(match.possession)
        self.assertLessEqual(match.pitch.distance(Location(.8, .5), match.ball_location), 4+1e-9)
        home, away = match.statistics("h"), match.statistics("a")
        self.assertEqual((home.shots, home.shots_blocked, home.shots_on_target), (1, 1, 0))
        self.assertEqual((away.blocks, away.saves), (1, 0))
        self.assertEqual((match.home_goals, match.away_goals), (0, 0))

    def test_parried_save_leaves_ball_uncontrolled_at_either_end(self):
        for team, player, location in (("h", "h-9", Location(.8, .5)),
                                       ("a", "a-9", Location(.2, .5))):
            match = self.make_match(ShotConfig(block_probability=0, parry_probability=1))
            match.start()
            match.set_possession(team, player, location=location)
            match.step()
            self.assertEqual([e.kind for e in match.events[-2:]], ["shot_parried", "ball_loose"])
            self.assertEqual(match.loose_ball.reason, "goalkeeper_parry")
            self.assertIsNone(match.possession)
            opponent = "a" if team == "h" else "h"
            self.assertEqual(match.statistics(opponent).saves, 1)
            self.assertEqual(match.statistics(opponent).parries, 1)
            self.assertEqual(match.statistics(team).shots_on_target, 1)
            index = len(match.events)
            match.step()
            self.assertEqual(len(match.events[index:]), 1)
            self.assertIn(match.events[-1].kind, ("ball_recovered", "ball_unrecovered"))

    def test_held_save_does_not_create_rebound(self):
        match = self.make_match(ShotConfig(block_probability=0, parry_probability=0))
        match.start()
        match.set_possession("h", "h-9", location=Location(.8, .5))
        match.step()
        self.assertEqual(match.events[-1].kind, "shot_saved")
        self.assertEqual(match.possession.player_id, "a-1")
        self.assertIsNone(match.loose_ball)

    def test_model_probabilities_are_unconditional_and_pre_outcome(self):
        config = ActionConfig()
        zone = Zone(2, 1)
        target, conditional = shot_probabilities(zone, config)
        results = [resolve_shot(zone, Random(seed), config, block_probability=.3, parry_probability=.5)
                   for seed in range(300)]
        self.assertEqual({r.outcome for r in results},
                         {"goal", "shot_saved", "shot_missed", "shot_blocked", "shot_parried"})
        self.assertEqual({r.on_target_probability for r in results}, {.7*target})
        self.assertEqual({r.goal_probability for r in results}, {.7*target*conditional})

    def test_rebounds_stay_in_play_and_within_displacement_budget(self):
        pitch = Pitch()
        self.assertEqual(rebound_location(Location(0, 0), pitch, Random(0), 0), Location(0, 0))
        for point in (Location(0, 0), Location(1, 1), Location(.5, .5)):
            for seed in range(20):
                result = rebound_location(point, pitch, Random(seed), 8)
                self.assertTrue(0 < result.x < 1 and 0 < result.y < 1)
                self.assertLessEqual(pitch.distance(point, result), 8+1e-3)

    def test_reproducible_full_match_reconciliation_and_batch_config(self):
        matches = [run_match(Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95))
                   for _ in range(2)]
        self.assertEqual(matches[0].events, matches[1].events)
        match = matches[0]
        home, away = match.statistics("h"), match.statistics("a")
        for own, opponent in ((home, away), (away, home)):
            self.assertEqual(own.shots_on_target, own.goals+opponent.saves)
            self.assertEqual(own.shots_blocked, opponent.blocks)
            self.assertLessEqual(own.shots_on_target+own.shots_blocked, own.shots)
            attempts = [e for e in match.events if e.team_id == own.team_id
                        and e.kind in ("goal", "shot_saved", "shot_missed", "shot_blocked", "shot_parried")]
            self.assertEqual(own.shots, len(attempts))
            self.assertAlmostEqual(own.expected_goals, sum(e.goal_probability for e in attempts))
        self.assertEqual(home.possession_seconds+away.possession_seconds+match.loose_ball_seconds+match.dead_ball_seconds, 5400)
        summary = run_batch(1, shot_config=ShotConfig(enabled=False))
        self.assertFalse(summary["shot_configuration"]["enabled"])
        self.assertEqual(summary["team_averages"]["home"]["blocks"], 0)
        self.assertEqual(summary["team_averages"]["home"]["parries"], 0)

    def test_configuration_validation(self):
        for values in ({"block_probability":1.1}, {"parry_probability":-.1},
                       {"block_radius":-1}, {"rebound_distance":float("nan")}, {"enabled":1}):
            with self.assertRaises(ValueError):
                ShotConfig(**values)
