from dataclasses import FrozenInstanceError, replace
import unittest

from fm95.actions import ActionConfig
from fm95.attributes import Attributes
from fm95.batch import run_batch, run_match
from fm95.boundaries import Boundary, BoundaryExit
from fm95.demo import demo_team
from fm95.fatigue import FatigueConfig, PlayerCondition
from fm95.match import Match, Phase
from fm95.pitch import Location
from fm95.positions import Position
from fm95.substitution_policy import AutoSubstitutionConfig, recommend, suitability
from fm95.substitutions import SubstitutionConfig


class SubstitutionPolicyTests(unittest.TestCase):
    def make_match(self, **policy):
        match = Match(demo_team("h", "Home", include_bench=True),
                      demo_team("a", "Away", include_bench=True), seed=95,
                      action_config=ActionConfig(interval_seconds=9999, foul_probability=0),
                      auto_substitution_config=AutoSubstitutionConfig(**policy))
        match.start()
        match.phase = Phase.SECOND_HALF
        match._period_number = 2
        match._period_start_seconds = 2700
        match._ends_switched = True
        match.elapsed_seconds = 4000
        return match

    def tired(self, match, player="h-9", energy=.4, seconds=1800):
        match._conditions[player] = PlayerCondition(energy=energy, seconds_played=seconds)

    def stop(self, match):
        match.award_out_of_play(BoundaryExit(Boundary.TOP, Location(.5, 1)), "h", "h-6")

    def test_pure_read_only_suggestion_prefers_exact_cover_and_records_condition(self):
        match = self.make_match()
        self.tired(match)
        before = (tuple(match.events), match.active_players("h"), match.conditions("h"), match._rng.getstate())
        decision, = match.substitution_recommendations("h")
        self.assertEqual((decision.outgoing_id, decision.incoming_id), ("h-9", "h-18"))
        self.assertEqual((decision.outgoing_energy, decision.incoming_energy, decision.suitability), (.4, 1, 1))
        self.assertGreater(decision.ability_gain, 0)
        self.assertEqual(before, (tuple(match.events), match.active_players("h"), match.conditions("h"), match._rng.getstate()))
        with self.assertRaises(FrozenInstanceError):
            decision.incoming_id = "h-13"

    def test_policy_is_opt_in_and_manual_suggestions_still_available(self):
        match = self.make_match()
        self.tired(match)
        match.step()
        self.assertEqual(match.statistics("h").automatic_substitutions, 0)
        self.assertEqual(len(match.substitution_recommendations("h")), 1)
        match.substitute("h", "h-9", "h-18")
        self.assertEqual(match.statistics("h").substitutions, 1)
        self.assertEqual(match.statistics("h").automatic_substitutions, 0)

    def test_enabled_policy_groups_changes_once_per_stoppage(self):
        match = self.make_match(enabled=True)
        for player in ("h-9", "h-8", "h-3"):
            self.tired(match, player)
        self.stop(match)
        match.step()
        stats = match.statistics("h")
        self.assertEqual((stats.substitutions, stats.automatic_substitutions, stats.substitution_windows), (2, 2, 1))
        events = [e for e in match.events if e.kind == "substitution"]
        self.assertTrue(all(e.reason == "fatigue" and e.outgoing_energy == .4 and e.incoming_energy == 1 for e in events))
        for _ in range(3):
            match.step()
        self.assertEqual(match.statistics("h").automatic_substitutions, 2)
        self.stop(match)
        match.step()
        self.assertEqual(match.statistics("h").automatic_substitutions, 3)
        self.assertEqual(match.statistics("h").substitution_windows, 2)

    def test_live_play_early_match_fresh_players_and_recent_substitutes_are_ignored(self):
        match = self.make_match(enabled=True)
        self.assertEqual(match.substitution_recommendations("h"), ())
        self.tired(match)
        match.set_possession("h", "h-9", location=Location(.5, .5))
        self.assertEqual(match.substitution_recommendations("h"), ())
        self.stop(match)
        match.elapsed_seconds = 1000
        self.assertEqual(match.substitution_recommendations("h"), ())
        match.elapsed_seconds = 4000
        self.tired(match, seconds=100)
        self.assertEqual(match.substitution_recommendations("h"), ())
        self.tired(match, energy=.7)
        self.assertEqual(match.substitution_recommendations("h"), ())

    def test_not_enough_condition_gain_or_ability_means_no_change(self):
        match = self.make_match()
        self.tired(match)
        self.tired(match, "h-18", energy=.45, seconds=0)
        self.assertEqual(match.substitution_recommendations("h"), ())
        match._conditions["h-18"] = PlayerCondition()
        bench = tuple(replace(p, attributes=Attributes(finishing=0, heading=0, dribbling=0))
                      if p.id == "h-18" else p for p in match.available_substitutes("h"))
        result = recommend(match.active_players("h"), bench, match.conditions("h"), 4000, 5,
                           match.auto_substitution_config, match.fatigue_config)
        self.assertEqual(result, ())

    def test_positional_fit_and_scarce_bench_players_are_respected(self):
        self.assertEqual(suitability(Position.ST, Position.CB), 0)
        self.assertEqual(suitability(Position.GK, Position.CB), 0)
        self.assertGreater(suitability(Position.CM, Position.DM), 0)
        match = self.make_match()
        for player in ("h-7", "h-8"):
            self.tired(match, player)
        bench = tuple(p for p in match.available_substitutes("h") if p.id == "h-15")
        decisions = recommend(match.active_players("h"), bench, match.conditions("h"), 4000, 5,
                              match.auto_substitution_config, match.fatigue_config)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].incoming_id, "h-15")
        self.assertEqual(decisions, recommend(match.active_players("h"), bench, match.conditions("h"),
                                             4000, 5, match.auto_substitution_config, match.fatigue_config))

    def test_limits_exhausted_windows_and_halftime_exemption(self):
        match = self.make_match(enabled=True)
        match.substitution_config = SubstitutionConfig(max_substitutions=1, max_windows=0)
        self.tired(match)
        self.assertEqual(match.substitution_recommendations("h"), ())
        match.phase = Phase.HALF_TIME
        match.elapsed_seconds = 2700
        match.resume()
        self.assertEqual(match.statistics("h").automatic_substitutions, 1)
        self.assertEqual(match.statistics("h").substitution_windows, 0)
        self.tired(match, "h-8")
        self.assertEqual(match.substitution_recommendations("h"), ())

    def test_halftime_recovery_is_considered_before_selecting_changes(self):
        match = self.make_match(enabled=True)
        match.phase = Phase.HALF_TIME
        match.elapsed_seconds = 2700
        self.tired(match, energy=.6)
        # Recovery to .7 puts this player above the default .65 threshold.
        self.assertEqual(match.substitution_recommendations("h"), ())
        match.resume()
        self.assertAlmostEqual(match.condition("h", "h-9").energy, .7)
        self.assertEqual(match.statistics("h").automatic_substitutions, 0)

    def test_bench_dismissals_and_previous_substitutes_are_not_selected(self):
        match = self.make_match()
        self.tired(match)
        match.issue_card("h", "h-18", "red")
        self.assertEqual(match.substitution_recommendations("h"), ())
        match = self.make_match()
        self.tired(match)
        match.substitute("h", "h-9", "h-18")
        self.assertFalse(any(d.outgoing_id == "h-9" or d.incoming_id == "h-18"
                             for d in match.substitution_recommendations("h")))

    def test_pending_restart_taker_is_protected(self):
        match = self.make_match(enabled=True)
        match.set_possession("h", "h-9", location=Location(.1, .5))
        match._award_foul(match.possession, match._active_team("h"), match._active_team("a"), "a-3", "take_on")
        # Protect the selected penalty taker regardless of their fatigue.
        taker = match.pending_restart.taker_id
        self.tired(match, taker)
        self.assertFalse(any(d.outgoing_id == taker for d in match.substitution_recommendations("h")))
        match.step()
        self.assertEqual(match.pending_restart.taker_id, taker)

    def test_new_changes_can_share_an_existing_manual_substitution_window(self):
        match = self.make_match(enabled=True)
        match.substitution_config = SubstitutionConfig(max_substitutions=5, max_windows=1)
        self.stop(match)
        match.substitute("h", "h-3", "h-13")
        self.tired(match)
        match.step()
        self.assertEqual(match.statistics("h").automatic_substitutions, 1)
        self.assertEqual(match.statistics("h").substitution_windows, 1)

    def test_empty_bench_disabled_fatigue_and_post_match_are_safe(self):
        match = Match(demo_team("h", "Home"), demo_team("a", "Away"),
                      auto_substitution_config=AutoSubstitutionConfig(enabled=True))
        match.start()
        self.assertEqual(match.substitution_recommendations("h"), ())
        match.phase = Phase.FULL_TIME
        self.assertEqual(match.substitution_recommendations("h"), ())
        data = run_batch(1, auto_substitution_config=AutoSubstitutionConfig(enabled=True),
                         fatigue_config=FatigueConfig(enabled=False))
        self.assertTrue(all(s["automatic_substitutions"] == 0 for s in data["team_averages"].values()))

    def test_full_matches_reproduce_and_use_legal_automatic_changes(self):
        config = AutoSubstitutionConfig(enabled=True)
        data = run_batch(1, auto_substitution_config=config)
        self.assertEqual(data, run_batch(1, auto_substitution_config=config))
        self.assertTrue(data["automatic_substitution_configuration"]["enabled"])
        self.assertGreater(sum(s["automatic_substitutions"] for s in data["team_averages"].values()), 0)
        for values in data["team_averages"].values():
            self.assertEqual(values["automatic_substitutions"], values["substitutions"])
            self.assertLessEqual(values["substitutions"], 5)
            self.assertLessEqual(values["substitution_windows"], 3)
        total = sum(s["possession_seconds"] for s in data["team_averages"].values())
        self.assertEqual(total + data["average_dead_ball_seconds"] + data["average_loose_ball_seconds"], 5400)

    def test_configuration_validation(self):
        for kwargs in ({"enabled": 1}, {"earliest_second": -1}, {"minimum_seconds_played": True},
                       {"max_changes_per_stoppage": 1.5}, {"condition_threshold": float("nan")},
                       {"minimum_suitability": 2}, {"minimum_energy_gain": -1}):
            with self.assertRaises(ValueError):
                AutoSubstitutionConfig(**kwargs)
