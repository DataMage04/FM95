import unittest

from fm95.match.mechanics.actions import ActionConfig
from fm95.match import Match
from fm95.match.spatial.pitch import CENTRE, Direction, Third, Zone
from main import demo_team


class PossessionTests(unittest.TestCase):
    def setUp(self):
        self.match = Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95,
                           action_config=ActionConfig(foul_probability=0))

    def test_kickoffs_and_stoppages(self):
        match = self.match
        self.assertIsNone(match.possession)
        match.start()
        self.assertEqual((match.possession.team_id, match.possession.player_id,
                          match.possession.zone), ("h", "h-9", CENTRE))
        for _ in range(2700):
            match.step()
        self.assertIsNone(match.possession)
        match.resume()
        self.assertEqual((match.possession.team_id, match.possession.player_id,
                          match.possession.zone), ("a", "a-9", CENTRE))
        for _ in range(2700):
            match.step()
        self.assertIsNone(match.possession)

    def test_directions_switch_without_moving_fixed_zones(self):
        match = self.match
        zone = Zone(0, 2)
        self.assertEqual(match.attacking_direction("h"), Direction.RIGHT)
        self.assertEqual(match.attacking_direction("a"), Direction.LEFT)
        self.assertEqual(zone.third_for(match.attacking_direction("h")), Third.DEFENSIVE)
        self.assertEqual(zone.third_for(match.attacking_direction("a")), Third.ATTACKING)
        match.start()
        for _ in range(2700):
            match.step()
        match.resume()
        self.assertEqual(match.attacking_direction("h"), Direction.LEFT)
        self.assertEqual(match.attacking_direction("a"), Direction.RIGHT)
        self.assertEqual(zone.third_for(match.attacking_direction("h")), Third.ATTACKING)

    def test_transfer_keeps_team_carrier_location_and_event_consistent(self):
        match = self.match
        match.start()
        match.step()
        match.set_possession("h", "h-5", Zone(2, 1))
        match.set_possession("a", "a-3", Zone(2, 1))
        state, event = match.possession, match.events[-1]
        self.assertEqual((state.team_id, state.player_id, state.zone),
                         (event.team_id, event.player_id, event.zone))
        self.assertEqual(event.elapsed_seconds, 1)
        self.assertEqual(state.zone.third_for(match.attacking_direction("a")), Third.DEFENSIVE)

    def test_invalid_transfers_leave_state_and_events_unchanged(self):
        match = self.match
        with self.assertRaises(RuntimeError):
            match.set_possession("h", "h-2", CENTRE)
        match.start()
        original = match.possession
        count = len(match.events)
        for team, player, zone in (("x", "h-2", CENTRE), ("h", "a-2", CENTRE),
                                   ("a", "missing", CENTRE), ("h", "h-2", (1, 1))):
            with self.assertRaises(ValueError):
                match.set_possession(team, player, zone)
            self.assertEqual(match.possession, original)
            self.assertEqual(len(match.events), count)
        with self.assertRaises(ValueError):
            match.attacking_direction("unknown")

    def test_zone_validation_and_relative_thirds(self):
        for column in range(3):
            for lane in range(3):
                zone = Zone(column, lane)
                self.assertEqual(zone.third_for(Direction.RIGHT),
                                 (Third.DEFENSIVE, Third.MIDDLE, Third.ATTACKING)[column])
                self.assertEqual(zone.third_for(Direction.LEFT),
                                 (Third.ATTACKING, Third.MIDDLE, Third.DEFENSIVE)[column])
        for column, lane in ((-1, 0), (3, 1), (1, 3), (1.0, 1), (True, 0)):
            with self.assertRaises(ValueError):
                Zone(column, lane)
