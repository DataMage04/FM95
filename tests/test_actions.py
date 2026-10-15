import unittest
from random import Random

from fm95.actions import ActionConfig, resolve_pass
from fm95.recovery import RecoveryConfig
from fm95.match import Match, Phase, Possession
from fm95.pitch import Direction, Zone
from main import demo_team


class PassingTests(unittest.TestCase):
    def make_match(self, probability=.85, interval=6):
        return Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95,
                     recovery_config=RecoveryConfig(enabled=False),
                     action_config=ActionConfig(interval, probability, shot_probability=0,
                                                dribble_probability=0))

    def advance(self, match, seconds):
        for _ in range(seconds):
            match.step()

    def test_success_and_interception(self):
        for probability, kind, owner in ((1, "pass_completed", "h"),
                                         (0, "pass_intercepted", "a")):
            match = self.make_match(probability)
            match.start()
            original = match.possession
            self.advance(match, 5)
            self.assertEqual(match.possession, original)
            match.step()
            event = match.events[-1]
            self.assertEqual(event.kind, kind)
            self.assertEqual(event.player_id, original.player_id)
            self.assertNotEqual(event.receiver_id, original.player_id)
            self.assertEqual(event.origin, original.zone)
            carrier = event.receiver_id if probability else event.interceptor_id
            self.assertEqual((match.possession.team_id, match.possession.player_id, match.possession.zone),
                             (owner, carrier, event.zone))
            self.assertEqual(event.team_id, "h")

    def test_reproducible_full_match_and_ownership(self):
        matches = [self.make_match() for _ in range(2)]
        for match in matches:
            match.start()
            while match.phase != Phase.FULL_TIME:
                if match.phase == Phase.HALF_TIME:
                    match.resume()
                else:
                    match.step()
                    if match.possession:
                        state = match.possession
                        team = match.home if state.team_id == "h" else match.away
                        self.assertIn(state.player_id, {p.id for p in team.lineup})
        self.assertEqual(matches[0].events, matches[1].events)
        self.assertTrue({"pass_completed", "pass_intercepted"}
                        <= {e.kind for e in matches[0].events})

    def test_whistle_priority_and_halftime_timer_reset(self):
        match = self.make_match(interval=7)
        match.start()
        self.advance(match, 2700)
        count = len(match.events)
        with self.assertRaises(RuntimeError):
            match.step()
        self.assertEqual(len(match.events), count)
        match.resume()
        self.advance(match, 6)
        self.assertEqual(match.events[-1].kind, "kickoff")
        match.step()
        self.assertEqual(match.events[-1].elapsed_seconds, 2707)
        self.advance(match, 5400 - match.elapsed_seconds)
        self.assertEqual(match.events[-1].kind, "full_time")
        self.assertFalse(any(e.kind.startswith("pass_") and e.elapsed_seconds in (2700, 5400)
                             for e in match.events))

    def test_destinations_are_adjacent_and_direction_is_symmetric(self):
        home, away = demo_team("h", "Home"), demo_team("a", "Away")
        for column in range(3):
            for lane in range(3):
                for seed in range(30):
                    origin = Zone(column, lane)
                    mirrored = Zone(2 - column, lane)
                    result = resolve_pass(Possession("h", "h-2", origin), home, away,
                                          Direction.RIGHT, Random(seed), ActionConfig())
                    reverse = resolve_pass(Possession("h", "h-2", mirrored), home, away,
                                           Direction.LEFT, Random(seed), ActionConfig())
                    self.assertLessEqual(abs(result.zone.column - column)
                                         + abs(result.zone.lane - lane), 1)
                    self.assertEqual(reverse.zone, Zone(2 - result.zone.column, result.zone.lane))
                    self.assertEqual(result.completed, reverse.completed)

    def test_invalid_configuration(self):
        for interval, probability in ((0, .5), (-1, .5), (1.5, .5), (True, .5),
                                      (6, -.1), (6, 1.1), (6, float("nan"))):
            with self.assertRaises(ValueError):
                ActionConfig(interval, probability)
