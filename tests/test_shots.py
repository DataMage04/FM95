import unittest
from random import Random

from fm95.actions import ActionConfig, choose_action
from fm95.recovery import RecoveryConfig
from fm95.match import Match, Phase
from fm95.pitch import CENTRE, Direction, Zone
from main import demo_team


class ShotTests(unittest.TestCase):
    def make_match(self, on_target=1, goal=1):
        return Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95,
                     recovery_config=RecoveryConfig(enabled=False),
                     action_config=ActionConfig(interval_seconds=1, shot_probability=1,
                         on_target_probability=on_target,
                         goal_given_on_target_probability=goal))

    def test_shots_require_attacking_third_for_both_directions(self):
        config = ActionConfig(shot_probability=1, dribble_probability=0)
        for direction in (Direction.LEFT, Direction.RIGHT):
            for column in range(3):
                expected = "shot" if column == (2 if direction == Direction.RIGHT else 0) else "pass"
                self.assertEqual(choose_action(Zone(column, 1), direction, Random(0), config), expected)
        self.assertEqual(choose_action(Zone(2, 1), Direction.RIGHT, Random(0),
                                      ActionConfig(shot_probability=0, dribble_probability=0)), "pass")

    def test_goals_credit_correct_team_and_restart_for_conceding_team(self):
        for scorer, carrier, column in (("h", "h-3", 2), ("a", "a-3", 0)):
            match = self.make_match()
            match.start()
            match.set_possession(scorer, carrier, Zone(column, 1))
            match.step()
            goal, kickoff = match.events[-2:]
            self.assertEqual((goal.kind, goal.team_id, goal.player_id), ("goal", scorer, carrier))
            self.assertEqual((match.home_goals, match.away_goals),
                             (1, 0) if scorer == "h" else (0, 1))
            opponent = "a" if scorer == "h" else "h"
            self.assertEqual((kickoff.kind, kickoff.team_id), ("kickoff", opponent))
            self.assertEqual(match.possession.team_id, opponent)
            self.assertEqual(match.possession.zone, CENTRE)
            self.assertEqual(goal.elapsed_seconds, kickoff.elapsed_seconds)

    def test_save_and_miss_give_keeper_possession_without_goal(self):
        for target, goal_chance, kind in ((1, 0, "shot_saved"), (0, 1, "shot_missed")):
            match = self.make_match(target, goal_chance)
            match.start()
            match.set_possession("h", "h-3", Zone(2, 0))
            match.step()
            shot = next(e for e in match.events if e.kind == kind)
            self.assertEqual(shot.goalkeeper_id, "a-1")
            self.assertEqual((match.home_goals, match.away_goals), (0, 0))
            self.assertEqual((match.possession.team_id, match.possession.player_id,
                              match.possession.zone), ("a", "a-1", Zone(2, 1)))
            self.assertEqual(match.events[-1].kind, "goal_kick" if target == 0 else kind)
            match.step()  # keeper can distribute on the following action
            self.assertTrue(match.events[-1].kind.startswith("pass_"))

    def test_second_half_shot_direction_and_no_action_on_whistle(self):
        match = self.make_match()
        match.start()
        for _ in range(2700):
            match.step()
        match.resume()
        match.set_possession("h", "h-3", Zone(0, 1))
        before = match.home_goals
        match.step()
        self.assertEqual(match.home_goals, before + 1)
        for _ in range(5400 - match.elapsed_seconds):
            match.step()
        self.assertFalse(any(e.kind in ("goal", "shot_saved", "shot_missed")
                             and e.elapsed_seconds in (2700, 5400) for e in match.events))

    def test_seeded_full_match_scores_reconcile_with_events(self):
        matches = [Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95)
                   for _ in range(2)]
        for match in matches:
            match.start()
            while match.phase != Phase.FULL_TIME:
                if match.phase == Phase.HALF_TIME:
                    match.resume()
                else:
                    match.step()
            for team_id, score in (("h", match.home_goals), ("a", match.away_goals)):
                self.assertEqual(score, sum(e.kind == "goal" and e.team_id == team_id
                                            for e in match.events))
            self.assertTrue({"goal", "shot_saved", "shot_missed"}
                            <= {e.kind for e in match.events})
        self.assertEqual(matches[0].events, matches[1].events)

    def test_invalid_shot_probabilities(self):
        for name in ("shot_probability", "on_target_probability", "goal_given_on_target_probability"):
            for value in (-.1, 1.1, float("nan")):
                with self.assertRaises(ValueError):
                    ActionConfig(**{name: value})
