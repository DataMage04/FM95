from dataclasses import replace
from random import Random
import unittest

from fm95.actions import ActionConfig, choose_action, dribble_success_chance, resolve_dribble
from fm95.attributes import Attributes
from fm95.recovery import RecoveryConfig
from fm95.batch import run_match
from fm95.demo import demo_team
from fm95.match import Match, Possession
from fm95.pitch import Direction, Zone


class DribblingTests(unittest.TestCase):
    def config(self, success=1):
        return ActionConfig(interval_seconds=1, shot_probability=0, dribble_probability=1,
                            dribble_success_probability=success, foul_probability=0)

    def test_forced_take_on_outcomes_and_statistics(self):
        for success in (0, 1):
            match = Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95,
                          recovery_config=RecoveryConfig(enabled=False),
                          action_config=self.config(success))
            match.start()
            original = match.possession
            match.step()
            event = match.events[-1]
            self.assertEqual(event.kind, "dribble_completed" if success else "dribble_tackled")
            self.assertEqual((event.player_id, event.team_id), (original.player_id, "h"))
            self.assertEqual(match.possession.player_id,
                             original.player_id if success else event.defender_id)
            self.assertEqual(match.possession.team_id, "h" if success else "a")
            self.assertEqual(match.possession.zone, Zone(2, 1) if success else original.zone)
            self.assertEqual(event.origin, original.zone)
            self.assertEqual(event.zone, match.possession.zone)
            self.assertEqual(event.dribble_success_probability, success)
            home, away = match.statistics("h"), match.statistics("a")
            self.assertEqual((home.dribbles_attempted, home.dribbles_completed), (1, success))
            self.assertEqual((away.tackles_attempted, away.tackles_won), (1, 1-success))
            self.assertEqual((home.passes_attempted, home.shots, away.interceptions), (0, 0, 0))

    def test_dribbling_and_tackling_change_opposed_chance(self):
        config = self.config(.6)
        neutral = dribble_success_chance(.5, .5, config)
        self.assertGreater(dribble_success_chance(.9, .5, config), neutral)
        self.assertLess(dribble_success_chance(.5, .9, config), neutral)
        self.assertEqual(dribble_success_chance(.9, .9, config), neutral)
        self.assertEqual(dribble_success_chance(1, 0, replace(config, attribute_strength=0)), .6)

    def test_actual_duel_attributes_are_recorded(self):
        match = Match(demo_team("h", "Home", attributes=Attributes(dribbling=.9)),
                      demo_team("a", "Away", attributes=Attributes(tackling=.7)),
                      action_config=self.config(.6), seed=95)
        match.start()
        match.step()
        event = match.events[-1]
        self.assertEqual((event.carrier_dribbling, event.defender_tackling), (.9, .7))
        self.assertEqual(event.dribble_success_probability,
                         dribble_success_chance(.9, .7, match.action_config))

    def test_progress_and_edges_for_both_directions(self):
        home, away = demo_team("h", "Home"), demo_team("a", "Away")
        for direction in (Direction.LEFT, Direction.RIGHT):
            for column in range(3):
                for lane in range(3):
                    origin = Zone(column, lane)
                    result = resolve_dribble(Possession("h", "h-9", origin), home, away,
                                              direction, Random(95), self.config())
                    self.assertEqual(abs(result.destination.column-column)
                                     + abs(result.destination.lane-lane), 1)
                    if 0 <= column + int(direction) <= 2:
                        self.assertEqual(result.destination, Zone(column+int(direction), lane))
                    else:
                        self.assertEqual(result.destination.column, column)
                    self.assertNotEqual(result.defender_id, "a-1")

    def test_goalkeeper_distributes_and_action_selection_can_disable_dribbles(self):
        match = Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95,
                      action_config=self.config())
        match.start()
        match.set_possession("h", "h-1", Zone(0, 1))
        match.step()
        self.assertTrue(match.events[-1].kind.startswith("pass_"))
        self.assertEqual(choose_action(Zone(1, 1), Direction.RIGHT, Random(0), self.config()), "dribble")
        self.assertEqual(choose_action(Zone(1, 1), Direction.RIGHT, Random(0),
                         replace(self.config(), dribble_probability=0)), "pass")

    def test_full_match_reconciliation_and_repeatability(self):
        matches = [run_match(Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95))
                   for _ in range(2)]
        self.assertEqual(matches[0].events, matches[1].events)
        home, away = matches[0].statistics("h"), matches[0].statistics("a")
        self.assertGreater(home.dribbles_attempted + away.dribbles_attempted, 0)
        for own, opponent in ((home, away), (away, home)):
            self.assertEqual(own.dribbles_attempted + opponent.presses_attempted, opponent.tackles_attempted)
            self.assertEqual(own.dribbles_attempted-own.dribbles_completed + opponent.presses_won,
                             opponent.tackles_won)
        self.assertEqual(home.possession_seconds+away.possession_seconds+matches[0].loose_ball_seconds, 5400)

    def test_validation(self):
        for name in ("dribbling", "tackling"):
            for value in (-1, 1.1, float("nan"), True):
                with self.assertRaises(ValueError):
                    Attributes(**{name: value})
        for name in ("dribble_probability", "dribble_success_probability"):
            for value in (-1, 1.1, float("nan")):
                with self.assertRaises(ValueError):
                    ActionConfig(**{name: value})
