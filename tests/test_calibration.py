import json
from dataclasses import replace
from pathlib import Path
import unittest
from random import Random
from unittest.mock import patch

from fm95.actions import ActionConfig, resolve_dribble
from fm95.calibration import load_profile, profile_configs
from fm95.crossing import CrossConfig
from fm95.defending import DefenseConfig
from fm95.demo import demo_team
from fm95.match import Match, Possession
from fm95.pitch import Location, Direction, Zone


class CalibrationTests(unittest.TestCase):
    def test_booked_caution_reduces_fouls_before_sanctions(self):
        home, away = demo_team("h", "H"), demo_team("a", "A")
        config = ActionConfig(foul_probability=1, booked_foul_multiplier=0)
        possession = Possession("h", "h-9", Zone(1, 1))
        booked = {p.id for p in away.lineup}
        self.assertTrue(resolve_dribble(possession, home, away, Direction.RIGHT, Random(1), config).fouled)
        self.assertFalse(resolve_dribble(possession, home, away, Direction.RIGHT, Random(1), config, booked_ids=booked).fouled)

    def test_source_parser_harmonizes_crosses_and_shot_outcomes(self):
        from tools.build_calibration_data import summarize
        events = [
            {"period": 1, "type": {"name": "Pass"}, "pass": {}},
            {"period": 2, "type": {"name": "Pass"}, "pass": {"cross": True, "type": {"name": "Corner"}}},
            {"period": 2, "type": {"name": "Shot"}, "shot": {"outcome": {"name": "Saved to Post"}}},
            {"period": 5, "type": {"name": "Shot"}, "shot": {"outcome": {"name": "Goal"}}},
        ]
        with patch("tools.build_calibration_data.download", return_value=json.dumps(events).encode()):
            counts = summarize({"match_id": 1, "match_date": "2015-01-01", "home_score": 0, "away_score": 0})["totals"]
        self.assertEqual((counts["passes_attempted"], counts["passes_completed"], counts["corners_taken"]), (1, 1, 1))
        self.assertEqual((counts["shots"], counts["shots_on_target"], counts["woodwork_contacts"]), (1, 1, 1))

    def test_area_foul_control_changes_generation_not_penalty_decision(self):
        for multiplier, expected in ((0, 0), (1, 1)):
            match = Match(demo_team("h", "H"), demo_team("a", "A"), seed=95,
                          action_config=ActionConfig(dribble_probability=1, shot_probability=0,
                              foul_probability=1, penalty_area_foul_multiplier=multiplier,
                              straight_red_probability=0, yellow_card_probability=0),
                          defense_config=DefenseConfig(press_attempt_probability=0),
                          cross_config=CrossConfig(enabled=False))
            match.start()
            match.set_possession("h", "h-9", location=Location(.94, .5))
            match._play_action()
            self.assertEqual(match.statistics("a").fouls_committed, expected)
            if expected:
                self.assertEqual(match.pending_restart.kind, "penalty")
                self.assertEqual(next(e for e in match.events if e.kind == "foul").foul_probability, 1)
            # Outside the box, the same base foul rate is preserved.
            match.set_possession("h", "h-9", location=Location(.5, .5))
            self.assertEqual(match._foul_probability(match.possession, match._active_team("a")), 1)

    def test_profile_loads_and_rejects_unknown_parameters(self):
        configs = profile_configs(load_profile())
        self.assertLess(configs["action_config"].interval_seconds, ActionConfig().interval_seconds)
        with self.assertRaises(ValueError):
            profile_configs({"unknown": {}})
        with self.assertRaises(TypeError):
            profile_configs({"actions": {"unknown": 1}})
        with self.assertRaises(ValueError):
            replace(ActionConfig(), penalty_area_foul_multiplier=-.1)

    def test_reference_split_and_manifest_are_disjoint_and_complete(self):
        path = Path(__file__).resolve().parents[1] / "data/calibration/targets.json"
        data = json.loads(path.read_text())
        self.assertEqual([data["groups"][k]["matches"] for k in ("train", "holdout")], [280, 100])
        ids = [r["match_id"] for r in data["manifest"]]
        self.assertEqual(len(ids), 380)
        self.assertEqual(len(set(ids)), 380)
        self.assertTrue(all(len(r["event_sha256"]) == 64 for r in data["manifest"]))


if __name__ == "__main__":
    unittest.main()
