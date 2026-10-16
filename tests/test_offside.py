from dataclasses import replace
import unittest
from unittest.mock import patch

from fm95.actions import ActionConfig, PassResult
from fm95.batch import run_batch, run_match
from fm95.boundaries import OutOfPlayConfig
from fm95.crossing import CrossConfig
from fm95.defending import DefenseConfig, Pressure
from fm95.demo import demo_team
from fm95.goalkeeping import KeeperCrossConfig
from fm95.match import Match, Restart, Phase
from fm95.offside import OffsideConfig, snapshot
from fm95.pitch import Direction, Location, Zone
from fm95.recovery import RecoveryConfig
from fm95.through_balls import ThroughBallConfig


class OffsideTests(unittest.TestCase):
    def make_match(self, *, through=False, enabled=True):
        match = Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95,
            action_config=ActionConfig(interval_seconds=1, shot_probability=0, dribble_probability=0),
            defense_config=DefenseConfig(enabled=False), out_config=OutOfPlayConfig(enabled=False),
            cross_config=CrossConfig(enabled=False, delivery_probability=1),
            keeper_cross_config=KeeperCrossConfig(enabled=False),
            recovery_config=RecoveryConfig(misplaced_pass_probability=1, movement_speed=200),
            through_ball_config=ThroughBallConfig(enabled=through, choice_probability=1,
                                                  completion_probability=1),
            offside_config=OffsideConfig(enabled=enabled))
        match.start()
        match.set_possession("h", "h-6", location=Location(.4, .5))
        for player in match.home.lineup:
            match._player_locations[player.id] = Location(.3, .5)
        for player in match.away.lineup:
            match._player_locations[player.id] = Location(.7, .5)
        match._player_locations["a-1"] = Location(.95, .5)
        match._player_locations["h-9"] = Location(.8, .5)
        match._sync_carrier_location()
        return match

    def context(self, match):
        return match._offside_snapshot(match.possession, match._active_team("h"), match._active_team("a"))

    def play_pass(self, match, completed=True):
        team = match.pending_restart.team_id if match.pending_restart else match.possession.team_id
        other = "a" if team == "h" else "h"
        with patch("fm95.match.resolve_pass", return_value=PassResult(
                f"{team}-9", Zone(2, 1), completed, None if completed else f"{other}-3", 1 if completed else 0)):
            match.step()

    def test_halfway_ball_and_second_last_opponent_ties_are_onside(self):
        match = self.make_match()
        for player_x, ball_x, expected in ((.8, .4, True), (.7, .4, False),
                (.5, .4, False), (.49, .2, False), (.8, .8, False), (.8, .9, False)):
            with self.subTest(player_x=player_x, ball_x=ball_x):
                match.set_possession("h", "h-6", location=Location(ball_x, .5))
                match._player_locations["h-9"] = Location(player_x, .5)
                context = self.context(match)
                self.assertEqual(context.position("h-9") is not None, expected)
                mirrored = snapshot("h", "h-6", match.possession.location.rotated(),
                    match.active_players("h"), match.active_players("a"),
                    {k: v.rotated() for k, v in match._player_locations.items()}, Direction.LEFT)
                self.assertEqual(mirrored.position("h-9") is not None, expected)

    def test_goalkeeper_is_not_assumed_last_opponent_and_dismissed_players_excluded(self):
        match = self.make_match()
        match._player_locations["a-1"] = Location(.6, .5)
        match._player_locations["a-2"] = Location(.95, .5)
        match._player_locations["a-3"] = Location(.85, .5)
        self.assertIsNone(self.context(match).position("h-9"))
        match.issue_card("a", "a-3", "red")
        self.assertIsNotNone(self.context(match).position("h-9"))

    def test_completed_pass_becomes_offside_and_dead_ball_restart(self):
        match = self.make_match()
        self.play_pass(match)
        self.assertEqual([e.kind for e in match.events[-3:]],
                         ["pass_offside", "offside", "indirect_free_kick_awarded"])
        event = match.events[-2]
        self.assertEqual(event.player_id, "h-9")
        self.assertEqual(event.receiver_start_location, Location(.8, .5))
        self.assertEqual(event.offside_line_x, .7)
        self.assertIsNone(match.possession)
        self.assertEqual(match.pending_restart.location, event.location)
        self.assertEqual(match.pending_restart.team_id, "a")
        home, away = match.statistics("h"), match.statistics("a")
        self.assertEqual((home.passes_attempted, home.passes_completed, home.passes_offside, home.offsides),
                         (1, 0, 1, 1))
        self.assertEqual((away.free_kicks_awarded, away.indirect_free_kicks_awarded), (1, 1))
        before = len(match.events)
        self.play_pass(match)
        self.assertEqual(match.events[before].kind, "indirect_free_kick_taken")
        self.assertEqual(match.dead_ball_seconds, 1)
        self.assertEqual(match.statistics("a").indirect_free_kicks_taken, 1)
        self.assertFalse(any(e.kind == "shot_saved" for e in match.events))

    def test_through_ball_uses_start_not_end_of_run(self):
        match = self.make_match(through=True)
        match._player_locations["h-9"] = Location(.69, .5)
        match.step()
        event = next(e for e in match.events if e.pass_type == "through")
        self.assertEqual(event.kind, "pass_completed")
        self.assertGreater(event.location.x, .7)
        self.assertEqual(match.statistics("h").offsides, 0)
        match = self.make_match(through=True)
        match.step()
        self.assertEqual(match.statistics("h").through_balls_attempted, 1)
        self.assertEqual(match.statistics("h").through_balls_completed, 0)
        self.assertEqual(match.statistics("h").offsides, 1)

    def test_restart_exemptions_apply_only_to_direct_receipt(self):
        for kind in ("throw_in", "goal_kick", "corner", "free_kick", "indirect_free_kick"):
            with self.subTest(kind=kind):
                match = self.make_match()
                match._pending_restart = Restart(kind, "h", "h-6", match.possession.zone, match.ball_location)
                self.play_pass(match)
                exempt = kind in ("throw_in", "goal_kick", "corner")
                self.assertEqual(match.statistics("h").offsides, 0 if exempt else 1)
                if exempt:
                    match.set_possession("h", "h-6", location=Location(.4, .5))
                    match._player_locations["h-9"] = Location(.8, .5)
                    self.play_pass(match)
                    self.assertEqual(match.statistics("h").offsides, 1)

    def test_offside_position_alone_and_intercepted_pass_do_not_stop_play(self):
        match = self.make_match()
        match.recovery_config = RecoveryConfig(enabled=False)
        self.play_pass(match, completed=False)
        self.assertEqual(match.possession.team_id, "a")
        self.assertEqual(match.statistics("h").offsides, 0)
        match = self.make_match(enabled=False)
        self.play_pass(match)
        self.assertEqual(match.possession.player_id, "h-9")

    def test_loose_recovery_keeps_kick_snapshot_until_touch(self):
        match = self.make_match()
        self.play_pass(match, completed=False)
        self.assertIsNotNone(match.loose_ball.offside)
        point = match.loose_ball.location
        # Move the defensive line beyond the receiver after the original kick.
        for player in match.away.lineup:
            match._player_locations[player.id] = Location(.99, .99)
        match._player_locations["h-9"] = point
        with patch.object(match._rng, "choices", side_effect=lambda values, **kwargs: [
                next(v for v in values if v[1].id == "h-9")]):
            match.step()
        self.assertEqual(match.statistics("h").offsides, 1)
        self.assertIsNone(match.loose_ball)
        self.assertEqual(match.statistics("h").passes_offside, 0)  # Already counted as a loose pass.

    def test_aerial_challenge_checked_before_header_even_if_defender_would_win(self):
        match = self.make_match()
        context = self.context(match)
        match.set_loose_ball(Location(.9, .5), aerial=True, offside=context)
        with patch.object(match._rng, "choices", side_effect=lambda players, **kwargs: [
                next(p for p in players if p.id == ("h-9" if players[0].id.startswith("h") else "a-3"))]):
            match.step()
        self.assertEqual(match.statistics("h").offsides, 1)
        self.assertEqual(match.statistics("h").headed_shots, 0)
        self.assertFalse(any(e.kind == "aerial_won" for e in match.events))

    def test_cross_and_shot_rebound_store_snapshot_and_whistle_clears_it(self):
        match = self.make_match()
        match._play_cross(match.possession, match._active_team("h"), match._active_team("a"),
                          Pressure(None, None, 0), self.context(match))
        self.assertIsNotNone(match.loose_ball.offside.position("h-9"))
        match.elapsed_seconds = 2699
        match.step()
        self.assertEqual(match.phase, Phase.HALF_TIME)
        self.assertIsNone(match.loose_ball)
        match.resume()
        self.assertIsNone(match.loose_ball)
        match = self.make_match()
        match.action_config = replace(match.action_config, on_target_probability=1,
                                     goal_given_on_target_probability=0)
        match.shot_config = replace(match.shot_config, block_probability=0, parry_probability=1)
        match._play_shot(match.possession, match._active_team("h"), match._active_team("a"),
                         Pressure(None, None, 0))
        self.assertEqual(match.loose_ball.reason, "goalkeeper_parry")
        self.assertIsNotNone(match.loose_ball.offside.position("h-9"))

    def test_corner_cross_exemption_is_retained_until_aerial_contact(self):
        match = self.make_match()
        match.cross_config = replace(match.cross_config, enabled=True, corner_cross_probability=1)
        match._pending_restart = Restart("corner", "h", "h-6", match.possession.zone, match.ball_location)
        match.step()
        self.assertEqual(match.loose_ball.kind, "aerial")
        self.assertIsNone(match.loose_ball.offside)

    def test_second_half_offside_and_defender_recovery_reset(self):
        match = self.make_match()
        match.elapsed_seconds = 2699
        match.step()
        match.resume()
        match.set_possession("h", "h-6", location=Location(.6, .5))
        for player in match.away.lineup:
            match._player_locations[player.id] = Location(.3, .5)
        match._player_locations["a-1"] = Location(.05, .5)
        match._player_locations["h-9"] = Location(.2, .5)
        self.play_pass(match)
        self.assertEqual(match.statistics("h").offsides, 1)
        self.assertEqual(match.events[-2].offside_line_x, .3)
        match = self.make_match()
        self.play_pass(match, completed=False)
        point = match.loose_ball.location
        match._player_locations["a-3"] = point
        with patch.object(match._rng, "choices", side_effect=lambda values, **kwargs: [
                next(v for v in values if v[1].id == "a-3")]):
            match.step()
        self.assertEqual(match.possession.player_id, "a-3")
        self.assertIsNone(match.loose_ball)
        self.assertEqual(match.statistics("h").offsides, 0)

    def test_full_match_offside_accounting_and_disabled_batch(self):
        match = run_match(Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95))
        for own, other in ((match.statistics("h"), match.statistics("a")),
                           (match.statistics("a"), match.statistics("h"))):
            self.assertEqual(own.offsides+own.restart_second_touches, other.indirect_free_kicks_awarded)
            self.assertGreaterEqual(own.offsides, own.passes_offside)
            self.assertLessEqual(own.indirect_free_kicks_taken, own.indirect_free_kicks_awarded)
        summary = run_batch(1, offside_config=OffsideConfig(enabled=False))
        self.assertFalse(summary["offside_configuration"]["enabled"])
        self.assertTrue(all(s["offsides"] == 0 for s in summary["team_averages"].values()))

    def test_boolean_config_validation(self):
        with self.assertRaises(ValueError):
            OffsideConfig(enabled=1)
