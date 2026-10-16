from dataclasses import FrozenInstanceError, replace
import unittest

from fm95.match.mechanics.actions import ActionConfig
from fm95.players.attributes import Attributes
from fm95.match.simulation import run_batch
from fm95.match.mechanics.boundaries import Boundary, BoundaryExit
from fm95.players.demo import demo_team
from fm95.match.mechanics.defending import DefenseConfig
from fm95.match.systems.injuries import InjuryConfig, interval_chance
from fm95.match import Match, Phase
from fm95.match.spatial.pitch import Direction, Location
from fm95.match.spatial.positions import Position
from fm95.match.systems.substitution_policy import AutoSubstitutionConfig
from fm95.match.systems.substitutions import SubstitutionConfig


class InjuryTests(unittest.TestCase):
    def make_match(self, *, auto=False, bench=True, **injury):
        match = Match(demo_team("h", "Home", include_bench=bench), demo_team("a", "Away", include_bench=bench),
            seed=95, action_config=ActionConfig(interval_seconds=1, shot_probability=0, dribble_probability=0,
                                               foul_probability=0, yellow_card_probability=0, straight_red_probability=0),
            defense_config=DefenseConfig(enabled=False), injury_config=InjuryConfig(**injury),
            auto_substitution_config=AutoSubstitutionConfig(enabled=auto))
        match.start()
        match.set_possession("h", "h-9", location=Location(.5, .5))
        return match

    def test_match_ending_injury_removes_player_and_awards_drop(self):
        match = self.make_match()
        match.injure_player("h", "h-9")
        self.assertNotIn("h-9", {p.id for p in match.active_players("h")})
        self.assertIsNone(match.possession)
        self.assertEqual((match.pending_restart.kind, match.pending_restart.team_id), ("dropped_ball", "h"))
        self.assertEqual(match.pending_restart.location, Location(.5, .5))
        injury = match.injury("h", "h-9")
        self.assertEqual(injury.position, Position.ST)
        with self.assertRaises(FrozenInstanceError):
            injury.reason = "other"
        self.assertEqual(match.statistics("h").injuries, 1)
        self.assertFalse(match.discipline("h", "h-9").sent_off)
        before = (tuple(match.events), match.active_players("h"), match.pending_restart)
        with self.assertRaises(ValueError):
            match.injure_player("h", "h-9")
        self.assertEqual(before, (tuple(match.events), match.active_players("h"), match.pending_restart))

    def test_manual_replacement_of_injured_slot_preserves_history(self):
        match = self.make_match()
        match.injure_player("h", "h-9")
        match.substitute("h", "h-9", "h-18")
        self.assertEqual(len(match.active_players("h")), 11)
        self.assertIsNotNone(match.injury("h", "h-9"))
        self.assertEqual(match.statistics("h").forced_substitutions, 1)
        self.assertEqual(match.statistics("h").automatic_substitutions, 0)
        self.assertFalse(match.events[-1].automatic)
        with self.assertRaises(ValueError):
            match.substitute("h", "h-9", "h-13")
        with self.assertRaises(ValueError):
            match.set_possession("h", "h-9", location=Location(.5, .5))

    def test_automatic_forced_change_ignores_fatigue_timing_and_protects_roles(self):
        match = self.make_match(auto=True)
        match.injure_player("h", "h-9")
        decision, = match.injury_substitution_recommendations("h")
        self.assertEqual((decision.outgoing_id, decision.incoming_id), ("h-9", "h-18"))
        match.step()
        event = next(e for e in match.events if e.kind == "substitution")
        self.assertEqual((event.reason, event.automatic), ("injury", True))
        self.assertEqual(match.statistics("h").automatic_substitutions, 1)
        self.assertEqual(len(match.active_players("h")), 11)
        self.assertTrue(any(e.kind == "dropped_ball_taken" for e in match.events))
        self.assertEqual(match.dead_ball_seconds, 1)
        self.assertFalse(any(e.kind == "goal" for e in match.events))

    def test_exhausted_limits_or_empty_bench_leave_team_short(self):
        for bench, limit in ((False, 5), (True, 0)):
            match = self.make_match(auto=True, bench=bench)
            match.substitution_config = SubstitutionConfig(max_substitutions=limit)
            match.injure_player("h", "h-9")
            match.step()
            self.assertEqual(len(match.active_players("h")), 10)
            self.assertEqual(match.statistics("h").substitutions, 0)
            self.assertEqual(match.phase, Phase.FIRST_HALF)

    def test_forced_change_can_use_weak_or_out_of_position_reserve(self):
        match = self.make_match(auto=True)
        # Only a defender remains available to replace the injured striker.
        for player in match.home.bench:
            if player.id != "h-13":
                match.issue_card("h", player.id, "red")
        match.injure_player("h", "h-9")
        match.step()
        incoming = next(p for p in match.active_players("h") if p.id == "h-13")
        self.assertEqual(incoming.position, Position.ST)
        self.assertEqual(match.statistics("h").forced_substitutions, 1)

    def test_injured_keeper_can_be_replaced_or_use_emergency_keeper(self):
        for has_keeper in (True, False):
            match = self.make_match(auto=True)
            if not has_keeper:
                match.issue_card("h", "h-12", "red")
            match.injure_player("h", "h-1")
            self.assertEqual([p.id for p in match.active_players("h") if p.is_goalkeeper], ["h-2"])
            match.step()
            self.assertEqual(len(match.active_players("h")), 11)
            keepers = [p.id for p in match.active_players("h") if p.is_goalkeeper]
            self.assertEqual(keepers, ["h-12"] if has_keeper else ["h-2"])
            self.assertEqual(match.statistics("h").forced_substitutions, 1)

    def test_drop_inside_area_is_for_defending_goalkeeper(self):
        match = self.make_match()
        match.set_possession("h", "h-9", location=Location(.9, .5))
        match.injure_player("h", "h-9")
        restart = match.pending_restart
        self.assertEqual((restart.kind, restart.team_id, restart.taker_id), ("dropped_ball", "a", "a-1"))

    def test_foul_restart_and_sanctions_survive_injury_to_victim(self):
        match = self.make_match(enabled=True, probability_per_second=0, foul_injury_probability=1)
        match.action_config = replace(match.action_config, yellow_card_probability=1)
        match.set_possession("h", "h-9", location=Location(.9, .5))
        match._award_foul(match.possession, match._active_team("h"), match._active_team("a"), "a-3", "take_on")
        self.assertIsNotNone(match.injury("h", "h-9"))
        self.assertEqual(match.pending_restart.kind, "penalty")
        self.assertEqual(match.statistics("a").yellow_cards, 1)
        self.assertEqual(match.statistics("h").dropped_balls_awarded, 0)
        self.assertEqual(match.statistics("h").penalties_awarded, 1)
        match.substitute("h", "h-9", "h-18")
        self.assertEqual(match.pending_restart.kind, "penalty")

    def test_existing_restart_taker_is_reassigned_if_injured(self):
        match = self.make_match()
        match.award_out_of_play(BoundaryExit(Boundary.TOP, Location(.5, 1)), "h", "h-9")
        taker = match.pending_restart.taker_id
        match.injure_player("a", taker)
        self.assertEqual(match.pending_restart.kind, "throw_in")
        self.assertNotEqual(match.pending_restart.taker_id, taker)
        match.step()
        self.assertTrue(any(e.kind == "throw_in_taken" for e in match.events))
        self.assertEqual(match.statistics("h").dropped_balls_awarded, 0)

    def test_minimum_player_rule_allows_manager_to_replace_before_restart(self):
        for auto in (False, True):
            match = self.make_match(auto=auto)
            for player in ("h-3", "h-4", "h-5", "h-6"):
                match.issue_card("h", player, "red")
            match.injure_player("h", "h-9")
            self.assertEqual(len(match.active_players("h")), 6)
            self.assertEqual(match.phase, Phase.FIRST_HALF)
            if not auto:
                match.substitute("h", "h-9", "h-18")
            match.step()
            self.assertEqual(len(match.active_players("h")), 7)
            self.assertEqual(match.phase, Phase.FIRST_HALF)

    def test_below_seven_without_replacement_abandons(self):
        match = self.make_match(bench=False)
        for player in ("h-3", "h-4", "h-5", "h-6"):
            match.issue_card("h", player, "red")
        match.injure_player("h", "h-9")
        self.assertEqual(match.phase, Phase.ABANDONED)
        self.assertIsNone(match.pending_restart)
        match = self.make_match()
        for player in ("h-3", "h-4", "h-5", "h-6"):
            match.issue_card("h", player, "red")
        match.injure_player("h", "h-9")
        match.step()  # A manual manager did not restore seven before allowing play.
        self.assertEqual(match.phase, Phase.ABANDONED)

    def test_injured_players_stop_accumulating_load_and_never_reenter_actions(self):
        match = self.make_match()
        match.injure_player("h", "h-9")
        snapshot = match.condition("h", "h-9")
        index = len(match.events)
        for _ in range(30):
            match.step()
        self.assertEqual(match.condition("h", "h-9"), snapshot)
        for event in match.events[index:]:
            for actor in (event.player_id, event.receiver_id, event.interceptor_id, event.goalkeeper_id,
                          event.defender_id, event.opponent_player_id):
                self.assertNotEqual(actor, "h-9")

    def test_generation_is_opt_in_and_interval_risk_directional(self):
        config = InjuryConfig(enabled=True)
        neutral = interval_chance(6, .5, 1, 1, config)
        self.assertGreater(interval_chance(6, .9, 1, 1, config), neutral)
        self.assertGreater(interval_chance(6, .5, .3, 1, config), neutral)
        self.assertGreater(interval_chance(12, .5, 1, 1, config), neutral)
        self.assertEqual(interval_chance(6, .9, 1, 0, config), neutral)
        match = self.make_match(enabled=True, probability_per_second=1, foul_injury_probability=0)
        match.step()
        self.assertEqual(sum(e.kind == "injury" for e in match.events), 1)
        self.assertEqual(match.pending_restart.kind, "dropped_ball")
        match = self.make_match(probability_per_second=1, foul_injury_probability=1)
        match.step()
        self.assertEqual(sum(e.kind == "injury" for e in match.events), 0)

    def test_config_and_override_validation(self):
        for kwargs in ({"enabled": 1}, {"probability_per_second": -1},
                       {"foul_injury_probability": float("nan")}, {"fatigue_risk_strength": -1}):
            with self.assertRaises(ValueError):
                InjuryConfig(**kwargs)
        for value in (-1, 2, True):
            with self.assertRaises(ValueError):
                Attributes(injury_proneness=value)
        match = self.make_match()
        before = tuple(match.events)
        for team, player in (("h", "a-9"), ("h", "h-18")):
            with self.assertRaises(ValueError):
                match.injure_player(team, player)
        self.assertEqual(tuple(match.events), before)
        match.phase = Phase.FULL_TIME
        with self.assertRaises(RuntimeError):
            match.injure_player("h", "h-9")

    def test_enabled_batch_reproduces_with_legal_forced_changes(self):
        config = InjuryConfig(enabled=True, probability_per_second=.00005)
        auto = AutoSubstitutionConfig(enabled=True)
        first = run_batch(1, injury_config=config, auto_substitution_config=auto)
        self.assertEqual(first, run_batch(1, injury_config=config, auto_substitution_config=auto))
        self.assertTrue(first["injury_configuration"]["enabled"])
        self.assertGreater(sum(s["injuries"] for s in first["team_averages"].values()), 0)
        for stats in first["team_averages"].values():
            self.assertLessEqual(stats["forced_substitutions"], stats["injuries"])
            self.assertLessEqual(stats["substitutions"], 5)
        self.assertEqual(sum(first["outcomes"].values()), 1)
