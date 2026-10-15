from dataclasses import FrozenInstanceError, replace
from random import Random
import unittest

from fm95.actions import ActionConfig, pass_completion_chance, resolve_pass, shot_probabilities
from fm95.attributes import Attributes
from fm95.batch import run_match
from fm95.demo import demo_team
from fm95.match import Match, Player, Team
from fm95.pitch import Direction, Zone


class AttributeTests(unittest.TestCase):
    def test_validation_and_immutability(self):
        for name in ("passing", "finishing", "shot_stopping"):
            for value in (-.1, 1.1, float("nan"), float("inf"), "high", True, None):
                with self.assertRaises(ValueError):
                    Attributes(**{name: value})
        with self.assertRaises(FrozenInstanceError):
            Attributes().passing = .8
        with self.assertRaises(ValueError):
            Player("p", "Player", attributes={})

    def test_better_passing_increases_completion(self):
        config = ActionConfig()
        chances = [pass_completion_chance(Zone(1, 1), Zone(2, 1), Direction.RIGHT,
                                          config, passing=value) for value in (0, .5, 1)]
        self.assertLess(chances[0], chances[1])
        self.assertLess(chances[1], chances[2])

    def test_finishing_and_keeper_have_separate_effects(self):
        zone, config = Zone(2, 1), ActionConfig()
        weak = shot_probabilities(zone, config, finishing=0)
        strong = shot_probabilities(zone, config, finishing=1)
        self.assertGreater(strong[0], weak[0])
        self.assertGreater(strong[1], weak[1])
        weak_keeper = shot_probabilities(zone, config, shot_stopping=0)
        strong_keeper = shot_probabilities(zone, config, shot_stopping=1)
        self.assertEqual(weak_keeper[0], strong_keeper[0])
        self.assertLess(strong_keeper[1], weak_keeper[1])

    def test_disabled_attributes_and_forced_outcomes(self):
        zone = Zone(2, 1)
        config = ActionConfig(attribute_strength=0)
        self.assertEqual(shot_probabilities(zone, config, finishing=1, shot_stopping=0),
                         shot_probabilities(zone, config))
        self.assertEqual(pass_completion_chance(zone, zone, Direction.RIGHT, config, passing=0),
                         pass_completion_chance(zone, zone, Direction.RIGHT, config, passing=1))
        for value in (0, 1):
            config = ActionConfig(completion_probability=value, on_target_probability=value,
                                  goal_given_on_target_probability=value)
            for attribute in (0, .5, 1):
                self.assertEqual(pass_completion_chance(zone, zone, Direction.RIGHT, config,
                                                       passing=attribute), value)
                self.assertEqual(shot_probabilities(zone, config, finishing=attribute,
                                                   shot_stopping=1-attribute), (value, value))
        for value in (-1, 1.1, float("nan")):
            with self.assertRaises(ValueError):
                ActionConfig(attribute_strength=value)

    def test_actual_passer_is_used_not_team_average(self):
        home, away = demo_team("h", "Home"), demo_team("a", "Away")
        lineup = tuple(replace(p, attributes=Attributes(passing=1)) if p.id == "h-2"
                       else p for p in home.lineup)
        match = Match(Team(home.id, home.name, lineup), away)
        match.start()
        match.set_possession("h", "h-2", Zone(1, 1))
        result = resolve_pass(match.possession, match.home, match.away, Direction.RIGHT,
                              Random(95), ActionConfig())
        self.assertEqual(result.completion_probability, pass_completion_chance(
            match.possession.zone, result.zone, Direction.RIGHT, ActionConfig(), passing=1))

    def test_shooter_and_defending_keeper_are_recorded_and_applied(self):
        match = Match(demo_team("h", "Home", attributes=Attributes(finishing=.9)),
                      demo_team("a", "Away", attributes=Attributes(shot_stopping=.8)), seed=95,
                      action_config=ActionConfig(interval_seconds=1, shot_probability=1))
        match.start()
        match.set_possession("h", "h-3", Zone(2, 1))
        match.step()
        shot = next(e for e in match.events if e.goal_probability is not None)
        self.assertEqual((shot.shooter_finishing, shot.goalkeeper_shot_stopping), (.9, .8))
        target, conditional = shot_probabilities(Zone(2, 1), match.action_config,
                                               finishing=.9, shot_stopping=.8)
        self.assertEqual(shot.on_target_probability, target)
        self.assertEqual(shot.goal_probability, target * conditional)

    def test_non_neutral_match_is_reproducible_and_reconciles(self):
        matches = [run_match(Match(
            demo_team("h", "Home", attributes=Attributes(.8, .7, .6)),
            demo_team("a", "Away", attributes=Attributes(.3, .4, .9)), seed=95)) for _ in range(2)]
        self.assertEqual(matches[0].events, matches[1].events)
        for team_id in ("h", "a"):
            stats = matches[0].statistics(team_id)
            self.assertEqual(stats.goals, sum(e.kind == "goal" and e.team_id == team_id
                                             for e in matches[0].events))
            self.assertAlmostEqual(stats.expected_goals,
                sum(e.goal_probability for e in matches[0].events
                    if e.team_id == team_id and e.goal_probability is not None))
