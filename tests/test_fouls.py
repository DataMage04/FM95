from fm95.boundaries import OutOfPlayConfig
from dataclasses import replace
import unittest

from fm95.actions import ActionConfig
from fm95.recovery import RecoveryConfig
from fm95.batch import run_match
from fm95.demo import demo_team
from fm95.match import Match, Phase
from fm95.pitch import CENTRE


class FoulTests(unittest.TestCase):
    def make_match(self):
        return Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95,
            recovery_config=RecoveryConfig(enabled=False),
                     out_config=OutOfPlayConfig(enabled=False),
            action_config=ActionConfig(interval_seconds=1, shot_probability=0,
                dribble_probability=1, foul_probability=1, completion_probability=1,
                straight_red_probability=0, yellow_card_probability=0))

    def test_foul_stops_take_on_and_awards_correct_team(self):
        match = self.make_match()
        match.start()
        original = match.possession
        match.step()
        foul, award = match.events[-2:]
        self.assertEqual((foul.kind, foul.team_id, foul.fouled_player_id),
                         ("foul", "a", original.player_id))
        self.assertTrue(foul.player_id.startswith("a-"))
        self.assertNotEqual(foul.player_id, "a-1")
        self.assertEqual(foul.zone, original.zone)
        self.assertEqual((award.kind, award.team_id, award.player_id),
                         ("free_kick_awarded", "h", original.player_id))
        self.assertEqual(match.possession, original)
        self.assertEqual((match.pending_restart.team_id, match.pending_restart.taker_id,
                          match.pending_restart.zone), ("h", original.player_id, CENTRE))
        home, away = match.statistics("h"), match.statistics("a")
        self.assertEqual((home.fouls_suffered, home.free_kicks_awarded, away.fouls_committed), (1, 1, 1))
        self.assertEqual((home.dribbles_attempted, away.tackles_attempted, away.tackles_won), (0, 0, 0))

    def test_pending_restart_forces_pass_instead_of_another_take_on(self):
        match = self.make_match()
        match.start()
        match.step()
        count = len(match.events)
        match.step()
        self.assertEqual([e.kind for e in match.events[count:]], ["free_kick_taken", "pass_completed"])
        self.assertIsNone(match.pending_restart)
        self.assertEqual(match.statistics("h").free_kicks_taken, 1)
        self.assertEqual(match.statistics("h").passes_attempted, 1)

    def test_restart_pass_can_be_intercepted(self):
        match = self.make_match()
        match.action_config = replace(match.action_config, completion_probability=0)
        match.start()
        match.step()
        match.step()
        self.assertEqual(match.events[-1].kind, "pass_intercepted")
        self.assertEqual(match.possession.team_id, "a")
        self.assertIsNone(match.pending_restart)

    def test_whistle_clears_restart_and_second_half_starts_fresh(self):
        match = self.make_match()
        match.start()
        for _ in range(2699):
            match.step()
        self.assertIsNotNone(match.pending_restart)
        match.step()
        self.assertEqual(match.phase, Phase.HALF_TIME)
        self.assertIsNone(match.pending_restart)
        match.resume()
        self.assertEqual(match.possession.team_id, "a")
        self.assertIsNone(match.pending_restart)
        for _ in range(2699):
            match.step()
        self.assertIsNotNone(match.pending_restart)
        match.step()
        self.assertIsNone(match.pending_restart)
        self.assertEqual(match.phase, Phase.FULL_TIME)

    def test_explicit_possession_override_clears_pending_restart(self):
        match = self.make_match()
        match.start()
        match.step()
        match.set_possession("a", "a-2", CENTRE)
        self.assertIsNone(match.pending_restart)

    def test_full_match_reconciles_fouls_and_restarts(self):
        matches = [run_match(Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95))
                   for _ in range(2)]
        self.assertEqual(matches[0].events, matches[1].events)
        match = matches[0]
        home, away = match.statistics("h"), match.statistics("a")
        self.assertGreater(home.fouls_committed+away.fouls_committed, 0)
        for own, opponent in ((home, away), (away, home)):
            self.assertEqual(own.fouls_suffered, opponent.fouls_committed)
            self.assertEqual(own.free_kicks_awarded, own.fouls_suffered)
            self.assertLessEqual(own.free_kicks_taken, own.free_kicks_awarded)
        self.assertEqual(home.possession_seconds+away.possession_seconds+match.loose_ball_seconds+match.dead_ball_seconds, 5400)

    def test_probability_validation(self):
        for probability in (-1, 1.1, float("nan")):
            with self.assertRaises(ValueError):
                ActionConfig(foul_probability=probability)
