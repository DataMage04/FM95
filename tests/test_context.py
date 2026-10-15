import unittest
from random import Random

from fm95.actions import (ActionConfig, adjust_probability, pass_completion_chance,
                          resolve_shot, shot_probabilities)
from fm95.batch import run_match
from fm95.demo import demo_team
from fm95.match import Match
from fm95.pitch import Direction, Zone


class ContextTests(unittest.TestCase):
    def test_pass_difficulty_ordering_and_pressure_proxy(self):
        config = ActionConfig()
        origin = Zone(1, 1)
        chance = lambda dest: pass_completion_chance(origin, dest, Direction.RIGHT, config)
        self.assertLess(chance(Zone(2, 1)), chance(Zone(1, 0)))
        self.assertLess(chance(Zone(1, 0)), chance(Zone(0, 1)))
        self.assertLess(chance(Zone(0, 1)), chance(origin))
        self.assertLess(pass_completion_chance(Zone(2, 1), Zone(2, 0), Direction.RIGHT, config),
                        chance(Zone(1, 0)))

    def test_pass_context_mirrors_for_opposite_directions(self):
        for column in range(3):
            for target in range(3):
                right = pass_completion_chance(Zone(column, 1), Zone(target, 0), Direction.RIGHT, ActionConfig())
                left = pass_completion_chance(Zone(2-column, 1), Zone(2-target, 0), Direction.LEFT, ActionConfig())
                self.assertEqual(right, left)

    def test_shot_quality_and_pre_outcome_probability(self):
        config = ActionConfig()
        central = shot_probabilities(Zone(2, 1), config)
        wide = shot_probabilities(Zone(2, 0), config)
        self.assertGreater(central[0], wide[0])
        self.assertGreater(central[0] * central[1], wide[0] * wide[1])
        self.assertEqual(wide, shot_probabilities(Zone(0, 2), config))
        results = [resolve_shot(Zone(2, 1), Random(seed), config) for seed in range(100)]
        self.assertEqual({r.outcome for r in results}, {"goal", "shot_saved", "shot_missed"})
        self.assertEqual({r.goal_probability for r in results}, {central[0] * central[1]})

    def test_neutral_context_and_probability_bounds(self):
        config = ActionConfig(context_strength=0)
        self.assertEqual(pass_completion_chance(Zone(1, 1), Zone(2, 1), Direction.RIGHT, config), .85)
        self.assertEqual(shot_probabilities(Zone(2, 0), config), (.4, .25))
        for base in (0, .01, .5, .99, 1):
            for multiplier in (.5, .75, 1, 1.25, 2):
                adjusted = adjust_probability(base, multiplier, 1)
                self.assertTrue(0 <= adjusted <= 1)
                if base in (0, 1):
                    self.assertEqual(adjusted, base)
        for value in (-1, 1.1, float("nan")):
            with self.assertRaises(ValueError):
                ActionConfig(context_strength=value)

    def test_recorded_probabilities_and_xg_sum(self):
        match = run_match(Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95))
        for event in match.events:
            if event.kind.startswith("pass_"):
                direction = (Direction.RIGHT if (event.team_id == "h") == (event.elapsed_seconds < 2700)
                             else Direction.LEFT)
                self.assertEqual(event.completion_probability,
                    pass_completion_chance(event.origin, event.zone, direction, match.action_config))
        for team in ("h", "a"):
            shots = [e for e in match.events if e.team_id == team
                     and e.kind in ("goal", "shot_saved", "shot_missed")]
            self.assertTrue(shots)
            for event in shots:
                target, conditional = shot_probabilities(event.zone, match.action_config)
                self.assertEqual(event.on_target_probability, target)
                self.assertEqual(event.goal_probability, target * conditional)
            self.assertAlmostEqual(match.statistics(team).expected_goals,
                                   sum(e.goal_probability for e in shots))
