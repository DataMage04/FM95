from collections import Counter
from dataclasses import replace
from random import Random
import unittest

from fm95.actions import ActionConfig, resolve_pass
from fm95.demo import demo_team
from fm95.match import Match, Player, Possession, Team
from fm95.pitch import Direction, Zone
from fm95.positions import Position, involvement_weight, operating_zone


class PositionTests(unittest.TestCase):
    def test_defaults_and_keeper_consistency(self):
        self.assertEqual(Player("p", "Player").position, Position.CM)
        self.assertEqual(Player("g", "Keeper", True).position, Position.GK)
        for keeper, position in ((False, Position.GK), (True, Position.ST), (False, "ST")):
            with self.assertRaises(ValueError):
                Player("p", "Invalid", keeper, position=position)

    def test_positions_rotate_with_ends_including_wings(self):
        for position in Position:
            right = operating_zone(position, Direction.RIGHT)
            left = operating_zone(position, Direction.LEFT)
            self.assertEqual(left, Zone(2-right.column, 2-right.lane))
        self.assertEqual(operating_zone(Position.LW, Direction.RIGHT), Zone(2, 2))
        self.assertEqual(operating_zone(Position.LW, Direction.LEFT), Zone(0, 0))
        match = Match(demo_team("h", "Home"), demo_team("a", "Away"))
        match.start()
        self.assertEqual(match.player_operating_zone("h", "h-11"), Zone(2, 2))
        for _ in range(2700):
            match.step()
        match.resume()
        self.assertEqual(match.player_operating_zone("h", "h-11"), Zone(0, 0))
        with self.assertRaises(ValueError):
            match.player_operating_zone("h", "a-2")

    def test_nearby_positions_have_higher_weights(self):
        destination = Zone(2, 1)
        self.assertGreater(involvement_weight(Position.ST, destination, Direction.RIGHT),
                           involvement_weight(Position.CB, destination, Direction.RIGHT))
        # The defending team faces the opposite way, placing its CB near this destination.
        self.assertGreater(involvement_weight(Position.CB, destination, Direction.LEFT),
                           involvement_weight(Position.ST, destination, Direction.LEFT))
        for position in Position:
            self.assertEqual(involvement_weight(position, destination, Direction.RIGHT),
                             involvement_weight(position, Zone(0, 1), Direction.LEFT))

    def test_receiver_and_interceptor_selection_uses_operating_zones(self):
        home, away = demo_team("h", "Home"), demo_team("a", "Away")
        config = ActionConfig(completion_probability=0)
        possession = Possession("h", "h-7", Zone(2, 1))
        receivers, interceptors = Counter(), Counter()
        rng = Random(95)
        for _ in range(600):
            result = resolve_pass(possession, home, away, Direction.RIGHT, rng, config)
            self.assertNotEqual(result.receiver_id, possession.player_id)
            self.assertNotEqual(result.receiver_id, "h-1")
            self.assertNotEqual(result.interceptor_id, "a-1")
            if result.zone == Zone(2, 1):
                receivers[result.receiver_id] += 1
                interceptors[result.interceptor_id] += 1
        self.assertGreater(receivers["h-9"], receivers["h-3"])
        self.assertGreater(interceptors["a-3"], interceptors["a-9"])

    def test_demo_shape_and_kickoff_preference_with_fallback(self):
        home, away = demo_team("h", "Home"), demo_team("a", "Away")
        positions = Counter(p.position for p in home.lineup)
        self.assertEqual(sum(positions[p] for p in (Position.CB, Position.LB, Position.RB)), 4)
        self.assertEqual(sum(positions[p] for p in (Position.CM, Position.DM)), 3)
        self.assertEqual(sum(positions[p] for p in (Position.ST, Position.LW, Position.RW)), 3)
        match = Match(home, away)
        match.start()
        self.assertEqual(match.possession.player_id, "h-9")
        no_striker = Team(home.id, home.name, tuple(replace(p, position=Position.CM)
                         if p.position == Position.ST else p for p in home.lineup))
        match = Match(no_striker, away)
        match.start()
        self.assertEqual(match.possession.player_id, "h-2")
