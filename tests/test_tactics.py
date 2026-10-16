from dataclasses import FrozenInstanceError, asdict, replace
from random import Random
import unittest
from unittest.mock import patch

from fm95.actions import ActionConfig, pass_completion_chance, resolve_pass
from fm95.batch import run_batch
from fm95.boundaries import Boundary, BoundaryExit, OutOfPlayConfig
from fm95.crossing import CrossConfig
from fm95.defending import DefenseConfig, Pressure
from fm95.demo import demo_team
from fm95.fatigue import FatigueConfig
from fm95.match import Match, Phase, Possession
from fm95.offside import OffsideConfig
from fm95.pitch import Direction, Location, Zone
from fm95.tactics import TeamTactics, action_interval, action_preferences, preference, preset
from fm95.through_balls import ThroughBallConfig


class TacticsTests(unittest.TestCase):
    def make_match(self, home=None, away=None, *, interval=6):
        match = Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95,
            action_config=ActionConfig(interval_seconds=interval, shot_probability=0, dribble_probability=0,
                                      foul_probability=0), defense_config=DefenseConfig(enabled=False),
            cross_config=CrossConfig(enabled=False), through_ball_config=ThroughBallConfig(enabled=False),
            out_config=OutOfPlayConfig(enabled=False), offside_config=OffsideConfig(enabled=False),
            fatigue_config=FatigueConfig(enabled=False), home_tactics=home, away_tactics=away)
        match.start()
        match.set_possession("h", "h-6", location=Location(.4, .5))
        return match

    def test_validation_and_immutable_team_scoped_instructions(self):
        for field in asdict(TeamTactics()):
            for value in (-1, 2, True, float("nan"), "high"):
                with self.assertRaises(ValueError):
                    TeamTactics(**{field: value})
        match = self.make_match()
        original = match.tactics("h")
        with self.assertRaises(FrozenInstanceError):
            original.tempo = 1
        match.set_tactics("h", TeamTactics(tempo=1))
        self.assertEqual(match.tactics("a"), TeamTactics())
        before = tuple(match.events)
        with self.assertRaises(ValueError):
            match.set_tactics("h", {})
        self.assertEqual(tuple(match.events), before)
        match.phase = Phase.FULL_TIME
        with self.assertRaises(RuntimeError):
            match.set_tactics("h", TeamTactics())

    def test_explicit_balanced_settings_preserve_default_match_behavior(self):
        first = self.make_match()
        second = self.make_match(TeamTactics(), TeamTactics())
        for _ in range(120):
            first.step()
            second.step()
        self.assertEqual(first.events, second.events)
        self.assertEqual(first.player_locations("h"), second.player_locations("h"))
        self.assertEqual(first.conditions("h"), second.conditions("h"))

    def test_tempo_cadence_is_owned_by_possessing_team_and_elapsed_time_is_real(self):
        for tempo in (0, .5, 1):
            match = self.make_match(TeamTactics(tempo=tempo), TeamTactics(tempo=1-tempo))
            expected = action_interval(6, match.tactics("h"))
            calls = []
            with patch.object(match, "_play_action", side_effect=lambda: calls.append(match._action_elapsed_seconds)):
                for _ in range(12):
                    match.step()
            self.assertEqual(len(calls), 12//expected)
            self.assertTrue(all(elapsed == expected for elapsed in calls))
            match.set_possession("a", "a-6", location=Location(.6, .5))
            self.assertEqual(match.current_action_interval(), action_interval(6, match.tactics("a")))
        self.assertLess(action_interval(6, TeamTactics(tempo=1)), action_interval(6, TeamTactics(tempo=0)))

    def test_restarts_and_loose_balls_keep_base_cadence(self):
        match = self.make_match(TeamTactics(tempo=1))
        self.assertLess(match.current_action_interval(), 6)
        match.award_out_of_play(BoundaryExit(Boundary.TOP, Location(.5, 1)), "h", "h-6")
        self.assertEqual(match.current_action_interval(), 6)
        match.set_possession("h", "h-6", location=Location(.4, .5))
        match.set_loose_ball(Location(.5, .5))
        self.assertEqual(match.current_action_interval(), 6)

    def test_live_shape_change_moves_targets_without_teleporting_players(self):
        match = self.make_match()
        points = match.player_locations("h")
        original = match.formation_reference_locations("h")
        match.set_tactics("h", TeamTactics(defensive_line=1, width=1))
        targets = match.formation_reference_locations("h")
        self.assertEqual(match.player_locations("h"), points)
        self.assertGreater(targets["h-3"].x, original["h-3"].x)
        self.assertGreater(abs(targets["h-11"].y-.5), abs(original["h-11"].y-.5))
        self.assertEqual(targets["h-1"], original["h-1"])
        self.assertEqual(match.statistics("h").tactical_changes, 1)
        match.set_tactics("h", match.tactics("h"))
        self.assertEqual(match.statistics("h").tactical_changes, 1)
        self.assertEqual(match.events[-1].tactics, match.tactics("h"))
        match.defense_config = DefenseConfig(press_attempt_probability=0)
        match._action_elapsed_seconds = 1
        match._update_defensive_positions(match._active_team("h"), match._active_team("a"))
        for player_id, point in match.player_locations("h").items():
            self.assertLessEqual(match.pitch.distance(points[player_id], point), 4+1e-9)

    def test_shape_rotates_with_ends_and_uses_only_active_players(self):
        match = self.make_match(TeamTactics(defensive_line=.9, width=.8))
        before = match.formation_reference_locations("h")
        match._ends_switched = True
        after = match.formation_reference_locations("h")
        for player_id in before:
            self.assertAlmostEqual(before[player_id].rotated().x, after[player_id].x)
            self.assertAlmostEqual(before[player_id].rotated().y, after[player_id].y)
        match.issue_card("h", "h-3", "red")
        self.assertNotIn("h-3", match.formation_reference_locations("h"))

    def test_pressing_changes_attempts_and_workload_without_win_bonus(self):
        for pressing, expected in ((0, False), (1, True)):
            match = self.make_match(away=TeamTactics(pressing=pressing))
            match.defense_config = DefenseConfig(press_attempt_probability=.25, press_win_probability=0)
            with patch.object(match._rng, "random", return_value=.2):
                stopped, attempted = match._try_press(match.possession, match._active_team("h"),
                                                     match._active_team("a"), Pressure("a-2", 0, 1))
            self.assertFalse(stopped)
            self.assertEqual(attempted, expected)
            if expected:
                self.assertEqual(match.events[-1].challenge_win_probability, 0)
        low = self.make_match(away=TeamTactics(pressing=0))
        high = self.make_match(away=TeamTactics(pressing=1))
        for match in (low, high):
            match.fatigue_config = FatigueConfig()
            match.step()
        self.assertLess(high.condition("a", "a-2").energy, low.condition("a", "a-2").energy)

    def test_action_preferences_change_choices_without_changing_shot_skill(self):
        base = ActionConfig()
        low = action_preferences(base, TeamTactics(shooting=0, dribbling=0))
        high = action_preferences(base, TeamTactics(shooting=1, dribbling=1))
        self.assertGreater(high.shot_probability, low.shot_probability)
        self.assertGreater(high.dribble_probability, low.dribble_probability)
        self.assertEqual(high.on_target_probability, low.on_target_probability)
        self.assertEqual(high.goal_given_on_target_probability, low.goal_given_on_target_probability)
        for endpoint in (0, 1):
            self.assertEqual(preference(endpoint, 0), endpoint)
            self.assertEqual(preference(endpoint, 1), endpoint)

    def test_cross_and_through_ball_preferences_reach_action_dispatch(self):
        for crossing, expected in ((0, False), (1, True)):
            match = self.make_match(TeamTactics(crossing=crossing), interval=1)
            match.cross_config = CrossConfig(choice_probability=.25, delivery_probability=1)
            match.set_possession("h", "h-11", location=Location(.8, .9))
            with patch.object(match._rng, "random", return_value=.3):
                match.step()
            self.assertEqual(any(e.kind == "cross_delivered" for e in match.events), expected)
        for through, expected in ((0, False), (1, True)):
            match = self.make_match(TeamTactics(through_balls=through), interval=1)
            match.through_ball_config = ThroughBallConfig(choice_probability=.2, completion_probability=1)
            with patch.object(match._rng, "random", return_value=.25):
                match.step()
            self.assertEqual(any(e.pass_type == "through" for e in match.events), expected)

    def test_direct_passing_adds_long_options_and_distance_carries_risk(self):
        class ForwardChoice:
            def choices(self, options, weights, k):
                if isinstance(options[0], Zone):
                    return [max(options, key=lambda zone: zone.column)]
                return [options[0]]
            def random(self):
                return 0
        match = self.make_match()
        possession = Possession("h", "h-6", Zone(0, 1))
        short = resolve_pass(possession, match.home, match.away, Direction.RIGHT,
                             ForwardChoice(), ActionConfig(), directness=0)
        direct = resolve_pass(possession, match.home, match.away, Direction.RIGHT,
                              ForwardChoice(), ActionConfig(), directness=1)
        self.assertEqual(short.zone.column, 1)
        self.assertEqual(direct.zone.column, 2)
        self.assertLess(direct.completion_probability, short.completion_probability)
        self.assertEqual(direct.completion_probability, pass_completion_chance(
            possession.zone, direct.zone, Direction.RIGHT, ActionConfig()))

    def test_long_pass_stats_and_restart_passes_are_consistent(self):
        found = False
        for seed in range(20):
            match = self.make_match(TeamTactics(passing_directness=1), interval=1)
            match._rng = Random(seed)
            match.set_possession("h", "h-6", location=Location(.2, .5))
            match.step()
            if any(e.pass_type == "long" for e in match.events):
                found = True
                stats = match.statistics("h")
                self.assertEqual(stats.long_passes_attempted, 1)
                self.assertLessEqual(stats.long_passes_completed, stats.passes_completed)
                break
        self.assertTrue(found)
        match = self.make_match(TeamTactics(passing_directness=1), TeamTactics(passing_directness=1), interval=1)
        match.award_out_of_play(BoundaryExit(Boundary.TOP, Location(.2, 1)), "h", "h-6")
        with patch("fm95.match.resolve_pass", wraps=resolve_pass) as resolver:
            match.step()
        self.assertEqual(resolver.call_args.kwargs["directness"], .5)

    def test_defensive_line_affects_offside_through_actual_positions(self):
        match = self.make_match()
        match.offside_config = OffsideConfig()
        match._player_locations["h-9"] = Location(.82, .5)
        for line, offside in ((0, False), (1, True)):
            match.set_tactics("a", TeamTactics(defensive_line=line))
            match._player_locations.update(match.formation_reference_locations("a"))
            snapshot = match._offside_snapshot(match.possession, match._active_team("h"), match._active_team("a"))
            self.assertEqual(snapshot.position("h-9") is not None, offside)

    def test_fast_tempo_scales_forward_run_to_actual_elapsed_seconds(self):
        match = self.make_match(TeamTactics(tempo=1))
        match.through_ball_config = ThroughBallConfig(choice_probability=1, completion_probability=1)
        for _ in range(3):
            match.step()
        event = next(e for e in match.events if e.pass_type == "through")
        self.assertAlmostEqual(match.pitch.distance(event.receiver_start_location, event.intended_location), 4)
        self.assertEqual(match._action_elapsed_seconds, 3)

    def test_styled_batch_reproduces_and_reconciles_time(self):
        home, away = preset("pressing"), preset("direct")
        first = run_batch(1, home_tactics=home, away_tactics=away)
        self.assertEqual(first, run_batch(1, home_tactics=home, away_tactics=away))
        self.assertEqual(first["home_tactics"], asdict(home))
        self.assertEqual(first["away_tactics"], asdict(away))
        seconds = sum(s["possession_seconds"] for s in first["team_averages"].values())
        self.assertEqual(seconds+first["average_loose_ball_seconds"]+first["average_dead_ball_seconds"], 5400)
        self.assertGreater(first["team_averages"]["away"]["long_passes_attempted"], 0)
