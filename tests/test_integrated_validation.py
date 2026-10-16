import unittest
from fm95.validation import run_validation,validate_statistics
from fm95.match import Match
from fm95.demo import demo_team

class IntegratedValidationTests(unittest.TestCase):
    def test_full_feature_scenario_replays_and_reconciles(self):
        report=run_validation(matches=1,seed=95)
        self.assertTrue(report['passed']);self.assertEqual(report['simulations'],2)
        self.assertGreater(report['state_checks'],10000)
        self.assertGreater(report['results'][0]['treatment_returns'],0)
    def test_validator_detects_inconsistent_score(self):
        match=Match(demo_team('h','H'),demo_team('a','A'))
        match.home_goals=1
        with self.assertRaises(AssertionError):validate_statistics(match)
