from fm95.boundaries import OutOfPlayConfig
from dataclasses import replace
import unittest

from fm95.actions import ActionConfig, pass_completion_chance, shot_probabilities, press_win_chance
from fm95.batch import run_match, run_batch
from fm95.defending import (DefenseConfig, defensive_targets, goal_side,
                            measure_pressure, move_towards)
from fm95.demo import demo_team
from fm95.recovery import RecoveryConfig
from fm95.match import Match, Phase
from fm95.pitch import Direction, Location, Pitch, Zone


class DefendingTests(unittest.TestCase):
    def config(self, win=1):
        return DefenseConfig(movement_speed=200, press_attempt_probability=1, press_win_probability=win)

    def make_match(self, win=1, foul=0):
        return Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95,
            recovery_config=RecoveryConfig(enabled=False),
                     out_config=OutOfPlayConfig(enabled=False),
            action_config=ActionConfig(interval_seconds=1, shot_probability=0, dribble_probability=0,
                foul_probability=foul, straight_red_probability=0, yellow_card_probability=0),
            defense_config=self.config(win))

    def test_press_win_prevents_carrier_action_and_preserves_location(self):
        match = self.make_match()
        match.start()
        original = match.possession
        match.step()
        event = match.events[-1]
        self.assertEqual(event.kind, "press_won")
        self.assertEqual((event.team_id, event.opponent_player_id), ("a", original.player_id))
        self.assertEqual(match.possession.player_id, event.player_id)
        self.assertEqual(match.possession.team_id, "a")
        self.assertEqual(match.ball_location, original.location)
        self.assertEqual(match.statistics("h").passes_attempted, 0)
        stats = match.statistics("a")
        self.assertEqual((stats.presses_attempted, stats.presses_won, stats.tackles_won), (1, 1, 1))

    def test_evaded_press_allows_one_carrier_action(self):
        match = self.make_match(win=0)
        match.start()
        match.step()
        self.assertEqual(match.events[-2].kind, "press_evaded")
        self.assertTrue(match.events[-1].kind.startswith("pass_"))
        self.assertEqual(match.statistics("a").presses_won, 0)
        self.assertEqual(match.statistics("a").presses_attempted, 1)

    def test_out_of_reach_defender_cannot_attempt_press(self):
        match = self.make_match()
        match.defense_config = replace(match.defense_config, movement_speed=0, challenge_radius=.1)
        match.start()
        self.assertGreater(match.pressure_on_ball().distance, .1)
        match.step()
        self.assertFalse(any(e.kind.startswith("press_") for e in match.events))

    def test_engine_movement_respects_speed_budget(self):
        match = self.make_match(win=0)
        match.defense_config = replace(match.defense_config, movement_speed=4)
        match.action_config = replace(match.action_config, completion_probability=1)
        match.start()
        before = match.player_locations("a")
        match.step()
        after = match.player_locations("a")
        distances = [match.pitch.distance(before[p], after[p]) for p in before]
        self.assertTrue(all(distance <= 4 + 1e-9 for distance in distances))
        self.assertTrue(any(distance > 0 for distance in distances))

    def test_pressing_foul_uses_existing_restart_and_sanctions(self):
        match = self.make_match(foul=1)
        match.action_config = replace(match.action_config, yellow_card_probability=1)
        match.start()
        original = match.possession
        match.step()
        self.assertEqual([e.kind for e in match.events[-4:]],
                         ["press_foul", "foul", "yellow_card", "free_kick_awarded"])
        self.assertIsNone(match.possession)
        self.assertEqual(match.pending_restart.location, original.location)
        self.assertEqual(match.statistics("a").pressing_fouls, 1)
        index = len(match.events)
        match.step()
        self.assertEqual(match.events[index].kind, "free_kick_taken")
        self.assertFalse(any(e.kind.startswith("press_") for e in match.events[index:]))

    def test_distance_pressure_and_probability_effects(self):
        players = demo_team("a", "Away").lineup[1:2]
        ball, pitch, config = Location(.5, .5), Pitch(), DefenseConfig()
        near = measure_pressure(players, {players[0].id: Location(.51, .5)}, ball, pitch, config)
        far = measure_pressure(players, {players[0].id: Location(.9, .5)}, ball, pitch, config)
        self.assertGreater(near.intensity, far.intensity)
        self.assertEqual(far.intensity, 0)
        action = ActionConfig()
        normal = pass_completion_chance(Zone(1, 1), Zone(2, 1), Direction.RIGHT, action)
        pressured = pass_completion_chance(Zone(1, 1), Zone(2, 1), Direction.RIGHT, action, pressure=1)
        self.assertLess(pressured, normal)
        normal_shot = shot_probabilities(Zone(2, 1), action)
        pressured_shot = shot_probabilities(Zone(2, 1), action, pressure=1)
        self.assertLess(pressured_shot[0], normal_shot[0])
        self.assertEqual(pressured_shot[1], normal_shot[1])
        self.assertGreater(press_win_chance(.9, .5, .4, 1), press_win_chance(.5, .5, .4, 1))
        self.assertLess(press_win_chance(.5, .9, .4, 1), press_win_chance(.5, .5, .4, 1))

    def test_movement_budget_marking_and_goal_side(self):
        pitch = Pitch()
        origin, target = Location(.1, .2), Location(.8, .8)
        moved = move_towards(origin, target, 4, pitch)
        self.assertAlmostEqual(pitch.distance(origin, moved), 4)
        self.assertEqual(move_towards(origin, target, 999, pitch), target)
        home, away = demo_team("h", "Home"), demo_team("a", "Away")
        defenders, attackers = (away.lineup[2], away.lineup[4]), (home.lineup[8], home.lineup[6])
        ball = Location(.5, .5)
        locations = {"a-3": Location(.51, .5), "a-5": Location(.7, .8),
                     "h-9": ball, "h-7": Location(.72, .8)}
        anchors = {"a-3": locations["a-3"], "a-5": locations["a-5"]}
        targets = defensive_targets(defenders, attackers, locations, anchors, "h-9", ball,
                                    Direction.LEFT, pitch, DefenseConfig())
        self.assertLess(pitch.distance(targets["a-3"], ball), 2)
        self.assertGreater(targets["a-5"].x, locations["h-7"].x)
        self.assertEqual(targets["a-5"].y, locations["h-7"].y)
        self.assertLess(goal_side(ball, Direction.RIGHT, 3, pitch).x, ball.x)

    def test_dismissed_players_and_keeper_distribution_are_protected(self):
        match = self.make_match()
        match.start()
        match.issue_card("a", "a-7", "red")
        self.assertNotIn("a-7", match.player_locations("a"))
        match.set_possession("h", "h-1", location=Location(.05, .5))
        self.assertEqual(match.pressure_on_ball().intensity, 0)
        match.step()
        self.assertTrue(match.events[-1].kind.startswith("pass_"))
        self.assertNotEqual(match.events[-1].pressing_player_id, "a-7")

    def test_disabled_defense_and_seeded_integration(self):
        disabled = DefenseConfig(enabled=False)
        summary = run_batch(1, defense_config=disabled)
        self.assertFalse(summary["defense_configuration"]["enabled"])
        self.assertEqual(summary["team_averages"]["home"]["presses_attempted"], 0)
        matches = [run_match(Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95))
                   for _ in range(2)]
        self.assertEqual(matches[0].events, matches[1].events)
        self.assertEqual(matches[0].player_locations("h"), matches[1].player_locations("h"))
        home, away = matches[0].statistics("h"), matches[0].statistics("a")
        self.assertGreater(home.presses_attempted+away.presses_attempted, 0)
        self.assertEqual(home.possession_seconds+away.possession_seconds+matches[0].loose_ball_seconds+matches[0].dead_ball_seconds, 5400)
        for own, other in ((home, away), (away, home)):
            self.assertEqual(own.tackles_attempted, own.presses_attempted+other.dribbles_attempted)
            self.assertEqual(own.tackles_won, own.presses_won+other.dribbles_attempted-other.dribbles_completed)

    def test_configuration_validation(self):
        for values in ({"movement_speed":-1}, {"pressure_radius":0}, {"challenge_radius":13},
                       {"marking_distance":float("nan")}, {"pressure_effect":1.1},
                       {"press_attempt_probability":-.1}, {"press_win_probability":float("nan")}):
            with self.assertRaises(ValueError):
                DefenseConfig(**values)
