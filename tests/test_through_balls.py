from fm95.match.mechanics.offside import OffsideConfig
import json
import unittest

from fm95.match.mechanics.actions import ActionConfig
from fm95.match.simulation import run_batch
from fm95.match.mechanics.boundaries import OutOfPlayConfig
from fm95.match.mechanics.crossing import CrossConfig
from fm95.match.mechanics.defending import DefenseConfig
from fm95.players.demo import demo_team
from fm95.match import Match
from fm95.match.spatial.pitch import Direction, Location, Pitch
from fm95.match.mechanics.recovery import RecoveryConfig
from fm95.match.mechanics.through_balls import ThroughBallConfig, completion_chance, forward_runs


class ThroughBallTests(unittest.TestCase):
    def make_match(self, completion=1, *, loose=False, out=False, enabled=True):
        match = Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95, offside_config=OffsideConfig(enabled=False),
            action_config=ActionConfig(interval_seconds=1, shot_probability=0, dribble_probability=0),
            defense_config=DefenseConfig(enabled=False), cross_config=CrossConfig(enabled=False),
            recovery_config=RecoveryConfig(enabled=loose, misplaced_pass_probability=1),
            out_config=OutOfPlayConfig(enabled=out, failed_pass_out_probability=1),
            through_ball_config=ThroughBallConfig(enabled=enabled, choice_probability=1,
                                                  completion_probability=completion))
        match.start()
        match.set_possession("h", "h-6", location=Location(.4, .5))
        return match

    def test_config_validation(self):
        for kwargs in ({"enabled": 1}, {"choice_probability": -1},
                       {"completion_probability": float("nan")}, {"run_distance": 0},
                       {"run_distance": float("inf")}):
            with self.assertRaises(ValueError):
                ThroughBallConfig(**kwargs)

    def test_runs_rotate_and_use_pitch_metres(self):
        players = demo_team("h", "Home").lineup
        locations = {p.id: Location(.7, .4) for p in players}
        locations["h-2"] = Location(.95, .4)  # Too close to goal for this run.
        pitch = Pitch(length=80)
        config = ThroughBallConfig(run_distance=8)
        runs = forward_runs(players, locations, "h-6", Location(.4, .5), Direction.RIGHT, pitch, config)
        self.assertNotIn("h-1", [r[0] for r in runs])
        self.assertNotIn("h-2", [r[0] for r in runs])
        self.assertNotIn("h-6", [r[0] for r in runs])
        rotated = forward_runs(players, {k: v.rotated() for k, v in locations.items()},
                               "h-6", Location(.4, .5).rotated(), Direction.LEFT, pitch, config)
        for original, reverse in zip(runs, rotated):
            self.assertEqual(original[0], reverse[0])
            self.assertAlmostEqual(pitch.distance(original[1], original[2]), 8)
            self.assertAlmostEqual(original[2].rotated().x, reverse[2].x)

    def test_ability_pressure_and_neutral_strength(self):
        config = ThroughBallConfig()
        neutral = completion_chance(.5, 0, 1, .4, config)
        self.assertGreater(completion_chance(.9, 0, 1, .4, config), neutral)
        self.assertLess(completion_chance(.5, 1, 1, .4, config), neutral)
        self.assertEqual(completion_chance(.9, 0, 0, .4, config), neutral)

    def test_completed_run_and_stats(self):
        match = self.make_match()
        match.step()
        event = next(e for e in match.events if e.pass_type == "through")
        self.assertEqual(event.kind, "pass_completed")
        self.assertEqual(match.possession.player_id, event.receiver_id)
        self.assertEqual(match.ball_location, event.intended_location)
        self.assertAlmostEqual(match.pitch.distance(event.receiver_start_location, event.location), 8)
        self.assertEqual(match.player_locations("h")[event.receiver_id], event.location)
        stats = match.statistics("h")
        self.assertEqual((stats.passes_attempted, stats.passes_completed,
                          stats.through_balls_attempted, stats.through_balls_completed), (1, 1, 1, 1))

    def test_failure_routes_and_accounting(self):
        for loose, out, kind in ((False, False, "pass_intercepted"),
                                 (True, False, "pass_loose"), (True, True, "pass_out")):
            with self.subTest(kind=kind):
                match = self.make_match(0, loose=loose, out=out)
                match.step()
                event = next(e for e in match.events if e.pass_type == "through")
                self.assertEqual(event.kind, kind)
                self.assertEqual(match.statistics("h").through_balls_completed, 0)
                if out:
                    self.assertIsNotNone(match.pending_restart)
                elif loose:
                    self.assertIsNotNone(match.loose_ball)
                else:
                    self.assertEqual(match.possession.team_id, "a")
                    self.assertEqual(match.possession.player_id, event.interceptor_id)

    def test_disabled_and_restart_do_not_create_runs(self):
        match = self.make_match(enabled=False)
        match.step()
        self.assertFalse(any(e.pass_type == "through" for e in match.events))
        match = self.make_match(0, out=True)
        match.step()
        previous = sum(e.pass_type == "through" for e in match.events)
        match.step()
        self.assertEqual(sum(e.pass_type == "through" for e in match.events), previous)

    def test_batch_reproducible_and_serializable(self):
        first = run_batch(2)
        self.assertEqual(first, run_batch(2))
        self.assertEqual(json.loads(json.dumps(first)), first)
        self.assertIn("through_ball_configuration", first)
        self.assertGreater(first["team_averages"]["home"]["through_balls_attempted"], 0)
