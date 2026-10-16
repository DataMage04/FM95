import unittest

from fm95.actions import ActionConfig
from fm95.batch import run_batch, run_match
from fm95.demo import demo_team
from fm95.match import Match, Phase


class StatisticsTests(unittest.TestCase):
    def make_match(self, interval=6):
        return Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95,
                     action_config=ActionConfig(interval_seconds=interval))

    def test_zero_and_partial_possession_snapshots(self):
        match = self.make_match(interval=9999)
        original = match.statistics("h")
        self.assertEqual(original.possession_percentage, 0)
        self.assertEqual(original.pass_completion_percentage, 0)
        match.start()
        for _ in range(10):
            match.step()
        match.set_possession("a", "a-2", match.possession.zone)
        for _ in range(5):
            match.step()
        self.assertEqual(match.statistics("h").possession_seconds, 10)
        self.assertEqual(match.statistics("a").possession_seconds, 5)
        self.assertAlmostEqual(match.statistics("h").possession_percentage, 100 * 10 / 15)
        self.assertEqual(original.possession_seconds, 0)
        with self.assertRaises(ValueError):
            match.statistics("unknown")

    def test_full_match_reconciliation(self):
        match = run_match(self.make_match())
        home, away = match.statistics("h"), match.statistics("a")
        self.assertEqual(home.possession_seconds + away.possession_seconds + match.loose_ball_seconds + match.dead_ball_seconds, 5400)
        self.assertAlmostEqual(home.possession_percentage + away.possession_percentage, 100)
        self.assertEqual((home.goals, away.goals), (match.home_goals, match.away_goals))
        for own, other in ((home, away), (away, home)):
            self.assertEqual(own.passes_attempted - own.passes_completed,
                             other.interceptions + own.misplaced_passes + own.passes_out + own.passes_offside)
            self.assertEqual(own.shots_on_target, own.goals + other.saves)
            self.assertLessEqual(own.shots_on_target, own.shots)

    def test_half_time_does_not_accrue_possession(self):
        match = self.make_match(interval=9999)
        match.start()
        for _ in range(2700):
            match.step()
        self.assertEqual(match.phase, Phase.HALF_TIME)
        self.assertEqual(match.statistics("h").possession_seconds, 2700)
        with self.assertRaises(RuntimeError):
            match.step()
        match.resume()
        match.step()
        self.assertEqual(match.statistics("a").possession_seconds, 1)

    def test_batch_matches_individual_runs_and_reproduces(self):
        summary = run_batch(3, seed=95)
        self.assertEqual(summary, run_batch(3, seed=95))
        self.assertEqual(sum(summary["outcomes"].values()), 3)
        self.assertEqual(sum(summary["scorelines"].values()), 3)
        total_goals = 0
        for seed in range(95, 98):
            match = run_match(Match(demo_team("home", "Home"), demo_team("away", "Away"), seed=seed))
            total_goals += match.home_goals + match.away_goals
        self.assertAlmostEqual(summary["average_total_goals"], total_goals / 3)
        sides = summary["team_averages"]
        self.assertAlmostEqual(sum(s["possession_seconds"] for s in sides.values())
                               + summary["average_loose_ball_seconds"] + summary["average_dead_ball_seconds"], 5400)
        self.assertAlmostEqual(sum(s["possession_percentage"] for s in sides.values()), 100)

    def test_batch_empty_denominators_and_invalid_inputs(self):
        summary = run_batch(1, config=ActionConfig(interval_seconds=9999))
        self.assertEqual(summary["average_total_goals"], 0)
        self.assertEqual(summary["outcomes"]["draw"], 1)
        self.assertEqual(summary["team_averages"]["home"]["pass_completion_percentage"], 0)
        for count in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                run_batch(count)
