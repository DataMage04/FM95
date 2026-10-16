from dataclasses import FrozenInstanceError
import unittest

from fm95.actions import ActionConfig, pass_completion_chance
from fm95.attributes import Attributes
from fm95.batch import run_batch
from fm95.boundaries import Boundary, BoundaryExit
from fm95.crossing import CrossConfig
from fm95.defending import DefenseConfig
from fm95.demo import demo_team
from fm95.fatigue import (FatigueConfig, PlayerCondition, effective_attributes, movement_factor,
                          movement, tick)
from fm95.match import Match, Phase
from fm95.pitch import Location
from fm95.through_balls import ThroughBallConfig, forward_runs


class FatigueTests(unittest.TestCase):
    def make_match(self, *, stamina=.5, **fatigue):
        return Match(demo_team("h", "Home", attributes=Attributes(stamina=stamina), include_bench=True),
                     demo_team("a", "Away", include_bench=True), seed=95,
                     action_config=ActionConfig(interval_seconds=9999),
                     defense_config=DefenseConfig(enabled=False),
                     fatigue_config=FatigueConfig(**fatigue))

    def test_stamina_and_configuration_validation(self):
        for value in (-1, 2, float("nan"), True):
            with self.assertRaises(ValueError):
                Attributes(stamina=value)
        for kwargs in ({"enabled": 1}, {"drain_per_second": -1}, {"drain_per_metre": float("nan")},
                       {"halftime_recovery": 2}, {"effect_threshold": 0},
                       {"max_attribute_penalty": True}, {"max_movement_penalty": 1.1}):
            with self.assertRaises(ValueError):
                FatigueConfig(**kwargs)
        for kwargs in ({"energy": -1}, {"energy": float("nan")}, {"seconds_played": True},
                       {"distance_covered": -1}):
            with self.assertRaises(ValueError):
                PlayerCondition(**kwargs)

    def test_only_active_players_accumulate_time_and_load(self):
        match = self.make_match(drain_per_second=.01)
        initial = match.condition("h", "h-9")
        match.start()
        match.set_possession("h", "h-9", location=Location(.5, .5))
        for _ in range(10):
            match.step()
        striker, keeper, bench = (match.condition("h", player) for player in ("h-9", "h-1", "h-18"))
        self.assertAlmostEqual(striker.energy, .9)
        self.assertGreater(keeper.energy, striker.energy)
        self.assertEqual((striker.seconds_played, keeper.seconds_played, bench.seconds_played), (10, 10, 0))
        self.assertEqual(bench.energy, 1)
        self.assertEqual(initial.energy, 1)
        self.assertEqual(match.home.lineup[8].attributes.stamina, .5)
        with self.assertRaises(FrozenInstanceError):
            striker.energy = .5
        copy = match.conditions("h")
        copy.clear()
        self.assertEqual(len(match.conditions("h")), 18)
        with self.assertRaises(ValueError):
            match.condition("a", "h-9")

    def test_stamina_and_represented_running_change_depletion(self):
        config = FatigueConfig(drain_per_second=.1, drain_per_metre=.01)
        fresh = PlayerCondition()
        strong = tick(fresh, 1, False, False, config)
        weak = tick(fresh, 0, False, False, config)
        self.assertGreater(strong.energy, weak.energy)
        stationary = movement(strong, 0, 1, config)
        running = movement(strong, 10, 1, config)
        self.assertLess(running.energy, stationary.energy)
        self.assertEqual(running.distance_covered, 10)
        self.assertEqual(running.seconds_played, strong.seconds_played)

    def test_stoppage_and_halftime_recovery_are_bounded_and_do_not_add_time(self):
        match = self.make_match(drain_per_second=.1, stoppage_recovery_per_second=.02,
                                halftime_recovery=.2)
        match.start()
        match.set_possession("h", "h-9", location=Location(.5, .5))
        for _ in range(5):
            match.step()
        before = match.condition("h", "h-9")
        match.award_out_of_play(BoundaryExit(Boundary.TOP, Location(.5, 1)), "h", "h-9")
        match.step()
        self.assertAlmostEqual(match.condition("h", "h-9").energy, before.energy+.02)
        match.elapsed_seconds = 2699
        match.step()
        snapshot = match.condition("h", "h-9")
        self.assertEqual(match.phase, Phase.HALF_TIME)
        with self.assertRaises(RuntimeError):
            match.step()
        self.assertEqual(match.condition("h", "h-9"), snapshot)
        match.resume()
        recovered = match.condition("h", "h-9")
        self.assertAlmostEqual(recovered.energy, min(1, snapshot.energy+.2))
        self.assertEqual(recovered.seconds_played, snapshot.seconds_played)
        self.assertEqual(match.condition("h", "h-18").energy, 1)

    def test_substitution_preserves_outgoing_condition_and_incoming_is_fresh(self):
        match = self.make_match(drain_per_second=.01)
        match.start()
        match.set_possession("h", "h-9", location=Location(.5, .5))
        for _ in range(10):
            match.step()
        match.award_out_of_play(BoundaryExit(Boundary.TOP, Location(.5, 1)), "h", "h-9")
        before = match.condition("h", "h-9")
        match.substitute("h", "h-9", "h-18")
        self.assertEqual(match.condition("h", "h-18"), PlayerCondition())
        match.set_possession("h", "h-18", location=Location(.5, .5))
        for _ in range(5):
            match.step()
        self.assertEqual(match.condition("h", "h-9"), before)
        self.assertEqual(match.condition("h", "h-18").seconds_played, 5)
        match.issue_card("h", "h-18", "red")
        dismissed = match.condition("h", "h-18")
        match.step()
        self.assertEqual(match.condition("h", "h-18"), dismissed)

    def test_effective_abilities_and_movement_decline_without_altering_base_attributes(self):
        attributes = Attributes(passing=.8, stamina=.9)
        config = FatigueConfig()
        tired = effective_attributes(attributes, .2, config)
        self.assertLess(tired.passing, attributes.passing)
        self.assertEqual(tired.stamina, attributes.stamina)
        self.assertEqual(attributes.passing, .8)
        self.assertEqual(effective_attributes(attributes, 1, config), attributes)
        self.assertLess(movement_factor(.2, config), movement_factor(1, config))
        self.assertTrue(all(0 <= effective_attributes(attributes, 0, config).__dict__[key] <= 1
                            for key in attributes.__dict__))

    def test_pass_uses_effective_attribute_and_records_it(self):
        match = self.make_match(drain_per_second=.1, effect_threshold=1)
        match.start()
        match.set_possession("h", "h-9", location=Location(.5, .5))
        for _ in range(5):
            match.step()
        match.action_config = ActionConfig(interval_seconds=1, shot_probability=0, dribble_probability=0)
        match.cross_config = CrossConfig(enabled=False)
        match.through_ball_config = ThroughBallConfig(enabled=False)
        match.step()
        event = next(e for e in match.events if e.kind.startswith("pass_"))
        self.assertLess(event.passer_passing, .5)
        self.assertEqual(event.passer_passing, match.effective_attributes("h", "h-9").passing)
        expected = pass_completion_chance(event.origin, event.intended_zone, match.attacking_direction("h"),
            match.action_config, passing=event.passer_passing, pressure=event.pressure,
            pressure_effect=match.defense_config.pressure_effect)
        self.assertEqual(event.completion_probability, expected)

    def test_movement_reach_and_run_targets_use_current_condition(self):
        match = self.make_match(drain_per_second=.2, effect_threshold=1, drain_per_metre=0)
        match.start()
        match.set_possession("h", "h-9", location=Location(.5, .5))
        for _ in range(3):
            match.step()
        player = next(p for p in match.active_players("h") if p.id == "h-2")
        origin = match.player_locations("h")[player.id]
        match._move_player(player, Location(.9, .5), 10)
        distance = match.pitch.distance(origin, match.player_locations("h")[player.id])
        self.assertLess(distance, 10)
        self.assertAlmostEqual(match.condition("h", player.id).distance_covered, distance)
        runs = forward_runs(match.active_players("h"), match.player_locations("h"), "h-9",
            Location(.1, .5), match.attacking_direction("h"), match.pitch, ThroughBallConfig(),
            movement_factors={p.id: match._movement_factor(p.id) for p in match.active_players("h")})
        run = next(run for run in runs if run[0] == "h-2")
        self.assertLess(match.pitch.distance(run[1], run[2]), 8)

    def test_administrative_repositioning_does_not_count_as_running(self):
        match = self.make_match()
        match.start()
        match.set_possession("h", "h-9", location=Location(.9, .9))
        self.assertEqual(match.condition("h", "h-9").distance_covered, 0)
        match._kickoff(match.home)
        self.assertEqual(match.condition("h", "h-9").distance_covered, 0)

    def test_disabled_mode_preserves_energy_and_abilities_but_tracks_playing_time(self):
        match = self.make_match(enabled=False, drain_per_second=1, drain_per_metre=1)
        match.start()
        match.set_possession("h", "h-9", location=Location(.5, .5))
        for _ in range(5):
            match.step()
        self.assertEqual(match.condition("h", "h-9").energy, 1)
        self.assertEqual(match.condition("h", "h-9").seconds_played, 5)
        self.assertEqual(match.effective_attributes("h", "h-9"), match.home.lineup[8].attributes)
        self.assertEqual(match._movement_factor("h-9"), 1)

    def test_energy_bounds_even_with_extreme_load_or_recovery(self):
        config = FatigueConfig(drain_per_second=100, drain_per_metre=100,
                               stoppage_recovery_per_second=100)
        tired = tick(PlayerCondition(), .5, False, False, config)
        self.assertEqual(tired.energy, 0)
        self.assertEqual(movement(tired, 10, .5, config).energy, 0)
        self.assertEqual(tick(tired, .5, False, True, config).energy, 1)

    def test_batch_condition_metadata_reproducibility_and_minutes_reconcile(self):
        config = FatigueConfig(enabled=False)
        first = run_batch(1, fatigue_config=config,
                          config=ActionConfig(foul_probability=0, yellow_card_probability=0))
        second = run_batch(1, fatigue_config=config,
                           config=ActionConfig(foul_probability=0, yellow_card_probability=0))
        self.assertEqual(first, second)
        self.assertFalse(first["fatigue_configuration"]["enabled"])
        for team in first["team_averages"].values():
            self.assertEqual(team["average_condition"], 1)
            self.assertEqual(team["player_seconds"], 11*5400)
            self.assertGreater(team["distance_covered"], 0)
