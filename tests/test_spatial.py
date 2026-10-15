from fm95.boundaries import OutOfPlayConfig
import unittest

from fm95.actions import ActionConfig
from fm95.recovery import RecoveryConfig
from fm95.batch import run_match
from fm95.demo import demo_team
from fm95.match import Match, Possession
from fm95.pitch import Direction, Location, Pitch, Zone


class SpatialTests(unittest.TestCase):
    def make_match(self, config=None):
        return Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95,
                     recovery_config=RecoveryConfig(enabled=False),
                     out_config=OutOfPlayConfig(enabled=False),
                     action_config=config)

    def test_location_validation_and_zone_boundaries(self):
        for x, y in ((-1, 0), (0, 1.1), (float("nan"), 0), (True, 0), ("0", 0)):
            with self.assertRaises(ValueError):
                Location(x, y)
        self.assertEqual(Location(0, 0).zone, Zone(0, 0))
        self.assertEqual(Location(1, 1).zone, Zone(2, 2))
        self.assertEqual(Location(1/3, 2/3).zone, Zone(1, 2))
        for column in range(3):
            for lane in range(3):
                zone = Zone(column, lane)
                self.assertEqual(Location.centre_of(zone).zone, zone)
                self.assertEqual(Location(1, 1).shifted_to(zone).zone, zone)

    def test_metric_geometry_and_penalty_area_edges(self):
        pitch = Pitch()
        centre = Location(.5, .5)
        self.assertEqual(pitch.metres(centre), (52.5, 34))
        self.assertEqual(pitch.from_metres(52.5, 34), centre)
        self.assertAlmostEqual(pitch.distance(Location(0, 0), pitch.from_metres(3, 4)), 5)
        boundary = pitch.from_metres(16.5, 34 + pitch.penalty_width/2)
        self.assertTrue(pitch.in_penalty_area(boundary, Direction.RIGHT))
        self.assertFalse(pitch.in_penalty_area(pitch.from_metres(16.51, 34), Direction.RIGHT))
        self.assertFalse(pitch.in_penalty_area(pitch.from_metres(10, 55), Direction.RIGHT))
        self.assertTrue(pitch.in_penalty_area(boundary.rotated(), Direction.LEFT))
        self.assertFalse(pitch.in_penalty_area(boundary, Direction.LEFT))
        for kwargs in ({"length":0}, {"width":float("nan")}, {"width":30}, {"length":32}):
            with self.assertRaises(ValueError):
                Pitch(**kwargs)

    def test_single_source_possession_and_invalid_updates_are_atomic(self):
        location = Location(.91, .55)
        possession = Possession("h", "h-9", location=location)
        self.assertEqual(possession.zone, location.zone)
        with self.assertRaises(ValueError):
            Possession("h", "h-9", Zone(0, 0), location=location)
        match = self.make_match()
        match.start()
        original = match.possession
        count = len(match.events)
        with self.assertRaises(ValueError):
            match.set_possession("h", "h-9", Zone(0, 0), location=location)
        self.assertEqual(match.possession, original)
        self.assertEqual(len(match.events), count)
        match.set_possession("h", "h-9", location=location)
        self.assertEqual(match.ball_location, location)
        self.assertEqual(match.events[-1].location, location)

    def test_shape_separates_duplicate_positions_and_rotates(self):
        match = self.make_match(ActionConfig(interval_seconds=9999))
        before = match.formation_reference_locations("h")
        self.assertNotEqual(before["h-3"], before["h-4"])
        self.assertNotEqual(before["h-7"], before["h-8"])
        self.assertLess(before["h-6"].x, before["h-7"].x)
        match.start()
        for _ in range(2700):
            match.step()
        match.resume()
        after = match.formation_reference_locations("h")
        for player in before:
            self.assertEqual(after[player], before[player].rotated())
        match.issue_card("h", "h-3", "red")
        self.assertNotIn("h-3", match.formation_reference_locations("h"))
        before.clear()  # Returned mapping is an independent snapshot.
        self.assertEqual(len(match.formation_reference_locations("h")), 10)

    def test_foul_restart_preserves_exact_location(self):
        config = ActionConfig(interval_seconds=1, dribble_probability=1, shot_probability=0,
                              foul_probability=1, yellow_card_probability=0, straight_red_probability=0)
        match = self.make_match(config)
        match.start()
        location = Location(.63, .42)
        match.set_possession("h", "h-9", location=location)
        match.step()
        self.assertEqual(match.pending_restart.location, location)
        self.assertEqual(match.ball_location, location)
        self.assertTrue(all(e.location == location for e in match.events[-2:]))
        match.issue_card("h", "h-9", "red")  # Development override of pending taker.
        self.assertEqual(match.ball_location, location)
        self.assertEqual(match.pending_restart.location, location)
        match.step()
        self.assertEqual(match.events[-2].kind, "free_kick_taken")
        self.assertEqual(match.events[-2].location, location)
        self.assertEqual(match.events[-1].origin_location, location)

    def test_full_match_events_preserve_spatial_consistency(self):
        match = run_match(self.make_match())
        passes = []
        for event in match.events:
            if event.location is not None:
                self.assertEqual(event.location.zone, event.zone)
            if event.origin_location is not None:
                self.assertEqual(event.origin_location.zone, event.origin)
            if event.kind.startswith("pass_"):
                passes.append(event)
                self.assertIsNotNone(event.location)
        self.assertTrue(any(e.location != Location.centre_of(e.zone) for e in passes))
        self.assertIsNone(match.ball_location)
