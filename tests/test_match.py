import unittest

from fm95.match import Match, Phase, Team
from main import demo_team


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.home = demo_team("h", "Home")
        self.away = demo_team("a", "Away")
        self.match = Match(self.home, self.away)

    def test_lifecycle_boundaries(self):
        self.match.start()
        for _ in range(2699):
            self.match.step()
        self.assertEqual(self.match.phase, Phase.FIRST_HALF)
        self.match.step()
        self.assertEqual(self.match.phase, Phase.HALF_TIME)
        with self.assertRaises(RuntimeError):
            self.match.step()
        self.match.resume()
        for _ in range(2700):
            self.match.step()
        self.assertEqual(self.match.phase, Phase.FULL_TIME)
        self.assertEqual(self.match.elapsed_seconds, 5400)
        self.assertEqual([(e.kind, e.elapsed_seconds, e.team_id) for e in self.match.events],
                         [("kickoff", 0, "h"), ("half_time", 2700, None),
                          ("kickoff", 2700, "a"), ("full_time", 5400, None)])
        with self.assertRaises(RuntimeError):
            self.match.step()

    def test_invalid_transitions(self):
        for action in (self.match.step, self.match.resume):
            with self.assertRaises(RuntimeError):
                action()
        self.match.start()
        with self.assertRaises(RuntimeError):
            self.match.start()
        with self.assertRaises(RuntimeError):
            self.match.resume()

    def test_invalid_lineups(self):
        for lineup in (self.home.lineup[:10], (self.home.lineup[0],) * 11,
                       self.home.lineup[1:] + (self.away.lineup[1],)):
            with self.assertRaises(ValueError):
                Team("bad", "Invalid", lineup)

    def test_invalid_opponents(self):
        with self.assertRaises(ValueError):
            Match(self.home, self.home)
        with self.assertRaises(ValueError):
            Match(self.home, Team("other", "Other", self.home.lineup))
