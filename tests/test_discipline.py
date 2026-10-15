from dataclasses import replace
import unittest

from fm95.actions import ActionConfig
from fm95.batch import run_batch, run_match
from fm95.demo import demo_team
from fm95.match import Match, Phase
from fm95.pitch import CENTRE, Zone


class DisciplineTests(unittest.TestCase):
    def make_match(self, config=None):
        return Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95,
                     action_config=config)

    def test_two_yellows_dismiss_and_preserve_starting_lineup(self):
        match = self.make_match()
        match.start()
        match.issue_card("h", "h-3", "yellow")
        self.assertEqual(match.discipline("h", "h-3").yellow_cards, 1)
        self.assertEqual(len(match.active_players("h")), 11)
        match.issue_card("h", "h-3", "yellow")
        self.assertEqual([e.kind for e in match.events[-2:]], ["yellow_card", "red_card"])
        self.assertEqual(match.events[-1].reason, "second_yellow")
        self.assertTrue(match.discipline("h", "h-3").sent_off)
        self.assertEqual(len(match.active_players("h")), 10)
        self.assertEqual(len(match.home.lineup), 11)
        stats = match.statistics("h")
        self.assertEqual((stats.yellow_cards, stats.red_cards), (2, 1))

    def test_card_validation_does_not_mutate_on_failure(self):
        match = self.make_match()
        with self.assertRaises(RuntimeError):
            match.issue_card("h", "h-2", "red")
        match.start()
        for team, player, card in (("h", "a-2", "red"), ("unknown", "h-2", "red"),
                                    ("h", "h-2", "blue")):
            count = len(match.events)
            with self.assertRaises(ValueError):
                match.issue_card(team, player, card)
            self.assertEqual(len(match.events), count)
        match.issue_card("h", "h-2", "red")
        self.assertEqual(match.discipline("h", "h-2").yellow_cards, 0)
        count = len(match.events)
        with self.assertRaises(ValueError):
            match.issue_card("h", "h-2", "yellow")
        self.assertEqual(len(match.events), count)
        with self.assertRaises(ValueError):
            match.set_possession("h", "h-2", CENTRE)

    def test_dismissed_players_never_reappear_in_action_selection(self):
        match = self.make_match()
        match.start()
        match.issue_card("h", "h-9", "red")  # current carrier and preferred kickoff taker
        match.issue_card("a", "a-3", "red")
        index = len(match.events)
        self.assertNotEqual(match.possession.player_id, "h-9")
        while match.phase not in (Phase.FULL_TIME, Phase.ABANDONED):
            if match.phase == Phase.HALF_TIME:
                match.resume()
            else:
                match.step()
        for event in match.events[index:]:
            for actor in (event.player_id, event.receiver_id, event.interceptor_id,
                          event.defender_id, event.goalkeeper_id, event.fouled_player_id):
                self.assertNotIn(actor, ("h-9", "a-3"))

    def test_goalkeeper_dismissal_assigns_emergency_keeper(self):
        config = ActionConfig(interval_seconds=1, shot_probability=1,
                              on_target_probability=1, goal_given_on_target_probability=0)
        match = self.make_match(config)
        match.start()
        match.issue_card("h", "h-1", "red")
        keepers = [p for p in match.active_players("h") if p.is_goalkeeper]
        self.assertEqual([p.id for p in keepers], ["h-2"])
        self.assertFalse(match.home.lineup[1].is_goalkeeper)
        match.set_possession("a", "a-9", Zone(0, 1))
        match.step()
        self.assertEqual(match.events[-1].goalkeeper_id, "h-2")
        self.assertEqual(match.possession.player_id, "h-2")

    def test_yellows_persist_across_halftime(self):
        match = self.make_match(ActionConfig(interval_seconds=9999))
        match.start()
        match.issue_card("h", "h-2", "yellow")
        for _ in range(2700):
            match.step()
        match.resume()
        match.issue_card("h", "h-2", "yellow")
        self.assertTrue(match.discipline("h", "h-2").sent_off)

    def test_automatic_red_follows_foul_and_awards_restart(self):
        config = ActionConfig(interval_seconds=1, shot_probability=0, dribble_probability=1,
                              foul_probability=1, straight_red_probability=1)
        match = self.make_match(config)
        match.start()
        match.step()
        self.assertEqual([e.kind for e in match.events[-3:]],
                         ["foul", "red_card", "free_kick_awarded"])
        offender = match.events[-2].player_id
        self.assertNotIn(offender, {p.id for p in match.active_players("a")})
        self.assertEqual(match.pending_restart.team_id, "h")
        match.step()
        self.assertEqual(match.events[-2].kind, "free_kick_taken")

    def test_automatic_yellow_follows_foul_without_dismissal(self):
        config = ActionConfig(interval_seconds=1, shot_probability=0, dribble_probability=1,
                              foul_probability=1, straight_red_probability=0, yellow_card_probability=1)
        match = self.make_match(config)
        match.start()
        match.step()
        self.assertEqual([e.kind for e in match.events[-3:]],
                         ["foul", "yellow_card", "free_kick_awarded"])
        self.assertEqual(len(match.active_players("a")), 11)

    def test_abandonment_and_batch_exclusion(self):
        match = self.make_match()
        match.start()
        for player in ("a-2", "a-3", "a-4", "a-5"):
            match.issue_card("a", player, "red")
        self.assertEqual(len(match.active_players("a")), 7)
        self.assertEqual(match.phase, Phase.FIRST_HALF)
        match.issue_card("a", "a-6", "red")
        self.assertEqual(match.phase, Phase.ABANDONED)
        self.assertIsNone(match.possession)
        self.assertIsNone(match.pending_restart)
        with self.assertRaises(RuntimeError):
            match.step()
        config = ActionConfig(interval_seconds=1, shot_probability=0, dribble_probability=1,
                              foul_probability=1, straight_red_probability=1)
        summary = run_batch(2, config=config)
        self.assertEqual(summary["completed_matches"], 0)
        self.assertEqual(summary["outcomes"]["abandoned"], 2)
        self.assertEqual(summary["scorelines"], {})
        self.assertEqual(summary["average_total_goals"], 0)

    def test_probability_validation(self):
        for field in ("straight_red_probability", "yellow_card_probability"):
            for value in (-1, 1.1, float("nan")):
                with self.assertRaises(ValueError):
                    ActionConfig(**{field: value})
