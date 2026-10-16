from dataclasses import FrozenInstanceError, replace
import unittest

from fm95.match.mechanics.actions import ActionConfig
from fm95.players.attributes import Attributes
from fm95.match.simulation import run_batch, run_match
from fm95.match.mechanics.boundaries import Boundary, BoundaryExit
from fm95.players.demo import demo_team
from fm95.match.mechanics.defending import DefenseConfig
from fm95.match.mechanics.crossing import CrossConfig
from fm95.match.mechanics.shooting import ShotConfig
from fm95.match import Match, Phase
from fm95.match.spatial.pitch import Location, Zone
from fm95.match.spatial.positions import Position
from fm95.match.systems.substitutions import SubstitutionConfig


class SubstitutionTests(unittest.TestCase):
    def make_match(self, **limits):
        return Match(demo_team("h", "Home", include_bench=True),
                     demo_team("a", "Away", include_bench=True), seed=95,
                     action_config=ActionConfig(interval_seconds=1, shot_probability=0, dribble_probability=0,
                                               foul_probability=0, yellow_card_probability=0),
                     substitution_config=SubstitutionConfig(**limits))

    def stop(self, match):
        match.award_out_of_play(BoundaryExit(Boundary.TOP, Location(.5, 1)), "h", next(p.id for p in match.active_players("h") if not p.is_goalkeeper))

    def state(self, match):
        return (match.active_players("h"), match.available_substitutes("h"),
                match.player_locations("h"), match.substitution_status("h"),
                match.possession, match.pending_restart, tuple(match.events))

    def test_named_bench_validation_and_cross_team_identity(self):
        home = demo_team("h", "Home", include_bench=True)
        self.assertEqual((len(home.lineup), len(home.bench), len(home.squad)), (11, 7, 18))
        with self.assertRaises(ValueError):
            replace(home, bench=(home.lineup[0],))
        away = demo_team("a", "Away", include_bench=True)
        with self.assertRaises(ValueError):
            Match(home, replace(away, bench=(home.bench[0],)))
        with self.assertRaises(ValueError):
            replace(home, bench=("not a player",))
        self.assertIsInstance(replace(home, bench=list(home.bench)).bench, tuple)

    def test_substitution_updates_active_team_without_changing_team_sheet(self):
        match = self.make_match()
        match.start()
        old = match.player_locations("h")["h-9"]
        original_lineup = match.home.lineup
        match.substitute("h", "h-9", "h-13")  # Natural CB inherits the ST slot.
        active = {p.id: p for p in match.active_players("h")}
        self.assertNotIn("h-9", active)
        self.assertEqual(active["h-13"].position, Position.ST)
        self.assertEqual(match.player_locations("h")["h-13"], old)
        self.assertEqual(match.possession.player_id, "h-13")
        self.assertEqual(match.home.lineup, original_lineup)
        self.assertEqual(match.home.bench[1].position, Position.CB)
        self.assertNotIn("h-13", {p.id for p in match.available_substitutes("h")})
        stats = match.statistics("h")
        self.assertEqual((stats.substitutions, stats.substitution_windows), (1, 1))
        self.assertEqual(match.substitution_status("h").remaining, 4)
        self.assertEqual(match.events[-1].outgoing_player_id, "h-9")
        self.assertEqual(match.events[-1].incoming_player_id, "h-13")

    def test_changes_require_stoppage_and_rejections_are_atomic(self):
        match = self.make_match()
        with self.assertRaises(RuntimeError):
            match.substitute("h", "h-9", "h-13")
        match.start()
        match.set_possession("h", "h-9", location=Location(.5, .5))
        before = self.state(match)
        with self.assertRaises(RuntimeError):
            match.substitute("h", "h-9", "h-13")
        self.assertEqual(self.state(match), before)
        self.stop(match)
        for changes in ((), (("h-9", "a-13"),), (("h-9", "h-3"),),
                        (("h-9", "h-13"), ("h-8", "missing")),
                        (("h-9", "h-13"), ("h-9", "h-14")),
                        (("h-9", "h-13"), ("h-8", "h-13")), (("missing", "h-13"),)):
            before = self.state(match)
            with self.assertRaises(ValueError):
                match.substitute_many("h", changes)
            self.assertEqual(self.state(match), before)

    def test_multiple_calls_share_stoppage_window_until_restart_taken(self):
        match = self.make_match(max_windows=1)
        match.start()
        self.stop(match)
        match.substitute_many("h", (("h-9", "h-13"), ("h-8", "h-14")))
        match.substitute("h", "h-7", "h-15")
        self.assertEqual((match.substitution_status("h").used,
                          match.substitution_status("h").windows_used), (3, 1))
        match.step()
        self.stop(match)
        before = self.state(match)
        with self.assertRaises(ValueError):
            match.substitute("h", "h-6", "h-16")
        self.assertEqual(self.state(match), before)

    def test_halftime_uses_player_allowance_but_no_window(self):
        match = self.make_match(max_substitutions=2, max_windows=0)
        match.start()
        match.elapsed_seconds = 2699
        match.step()
        self.assertEqual(match.phase, Phase.HALF_TIME)
        match.substitute_many("h", (("h-9", "h-13"), ("h-8", "h-14")))
        self.assertEqual((match.substitution_status("h").used,
                          match.substitution_status("h").windows_used), (2, 0))
        with self.assertRaises(ValueError):
            match.substitute("h", "h-7", "h-15")
        match.resume()
        self.assertEqual(len(match.active_players("h")), 11)
        self.assertNotIn("h-9", match.player_locations("h"))
        self.assertIn("h-13", match.formation_reference_locations("h"))

    def test_player_limit_and_snapshot_immutability(self):
        match = self.make_match(max_substitutions=1)
        match.start()
        original = match.substitution_status("h")
        match.substitute("h", "h-9", "h-13")
        with self.assertRaises(ValueError):
            match.substitute("h", "h-8", "h-14")
        self.assertEqual(original.used, 0)
        with self.assertRaises(FrozenInstanceError):
            original.used = 3

    def test_substituted_player_cannot_return_or_be_replaced_twice(self):
        match = self.make_match()
        match.start()
        match.substitute("h", "h-9", "h-13")
        match.substitute("h", "h-13", "h-14")
        for outgoing, incoming in (("h-8", "h-13"), ("h-8", "h-9"), ("h-9", "h-15")):
            with self.assertRaises(ValueError):
                match.substitute("h", outgoing, incoming)
        self.assertEqual(match.substitution_status("h").used, 2)

    def test_sent_off_player_cannot_be_replaced_and_bench_red_does_not_reduce_team(self):
        match = self.make_match()
        match.start()
        match.issue_card("h", "h-9", "red")
        with self.assertRaises(ValueError):
            match.substitute("h", "h-9", "h-13")
        self.assertEqual(len(match.active_players("h")), 10)
        match.issue_card("h", "h-13", "red")
        self.assertEqual(len(match.active_players("h")), 10)
        with self.assertRaises(ValueError):
            match.substitute("h", "h-8", "h-13")
        self.assertEqual(match.substitution_status("h").used, 0)

    def test_cards_belong_to_player_and_substitute_can_be_dismissed(self):
        match = self.make_match()
        match.start()
        match.issue_card("h", "h-9", "yellow")
        match.substitute("h", "h-9", "h-13")
        self.assertEqual(match.discipline("h", "h-9").yellow_cards, 1)
        self.assertEqual(match.discipline("h", "h-13").yellow_cards, 0)
        match.issue_card("h", "h-13", "red")
        self.assertEqual(len(match.active_players("h")), 10)
        with self.assertRaises(ValueError):
            match.set_possession("h", "h-13", Zone(1, 1))

    def test_goalkeeper_replacement_and_emergency_keeper_restoration(self):
        match = self.make_match()
        match.start()
        match.substitute("h", "h-1", "h-12")
        self.assertEqual([p.id for p in match.active_players("h") if p.is_goalkeeper], ["h-12"])
        with self.assertRaises(ValueError):
            match.substitute("h", "h-12", "h-13")
        match = self.make_match()
        match.start()
        with self.assertRaises(ValueError):
            match.substitute("h", "h-9", "h-12")
        match.issue_card("h", "h-1", "red")
        self.assertEqual([p.id for p in match.active_players("h") if p.is_goalkeeper], ["h-2"])
        match.substitute("h", "h-9", "h-12")
        self.assertEqual(len(match.active_players("h")), 10)
        active = {p.id: p for p in match.active_players("h")}
        self.assertEqual([p.id for p in active.values() if p.is_goalkeeper], ["h-12"])
        self.assertEqual(active["h-2"].position, Position.RB)
        self.assertEqual(match.player_locations("h")["h-2"], match.formation_reference_locations("h")["h-2"])

    def test_pending_restart_taker_transfers_to_incoming_player(self):
        match = self.make_match()
        match.start()
        self.stop(match)
        outgoing = match.pending_restart.taker_id
        incoming = "a-13"
        point = match.pending_restart.location
        match.substitute("a", outgoing, incoming)
        self.assertEqual(match.pending_restart.taker_id, incoming)
        self.assertEqual(match.pending_restart.location, point)
        match.step()
        taken = next(e for e in match.events if e.kind == "throw_in_taken")
        self.assertEqual(taken.player_id, incoming)

    def test_penalty_taker_substitute_uses_incoming_attributes(self):
        match = self.make_match()
        match.start()
        match.set_possession("h", "h-9", location=Location(.9, .5))
        match._award_foul(match.possession, match._active_team("h"), match._active_team("a"), "a-3", "take_on")
        outgoing = match.pending_restart.taker_id
        match.substitute("h", outgoing, "h-18")
        match.step()
        event = next(e for e in match.events if e.shot_type == "penalty")
        self.assertEqual((event.player_id, event.set_piece_ability), ("h-18", .5))

    def test_offside_snapshot_and_action_selection_use_only_current_players(self):
        match = self.make_match()
        match.start()
        match.substitute("h", "h-9", "h-18")
        match.substitute("a", "a-3", "a-13")
        index = len(match.events)
        match.set_possession("h", "h-18", location=Location(.8, .5))
        while match.phase not in (Phase.FULL_TIME, Phase.ABANDONED):
            if match.phase == Phase.HALF_TIME:
                match.resume()
            else:
                match.step()
        for event in match.events[index:]:
            for actor in (event.player_id, event.receiver_id, event.interceptor_id, event.defender_id,
                          event.goalkeeper_id, event.fouled_player_id, event.pressing_player_id,
                          event.opponent_player_id, event.blocking_player_id):
                self.assertNotIn(actor, ("h-9", "a-3"))
        self.assertEqual(match.statistics("h").substitutions, 1)
        self.assertEqual(match.statistics("h").possession_seconds + match.statistics("a").possession_seconds
                         + match.loose_ball_seconds + match.dead_ball_seconds, 5400)

    def test_shots_use_substitute_shooter_and_keeper_attributes(self):
        home, away = demo_team("h", "Home", include_bench=True), demo_team("a", "Away", include_bench=True)
        home = replace(home, bench=tuple(replace(p, attributes=Attributes(finishing=.9))
                                        if p.id == "h-18" else p for p in home.bench))
        away = replace(away, bench=tuple(replace(p, attributes=Attributes(shot_stopping=.8))
                                        if p.id == "a-12" else p for p in away.bench))
        match = Match(home, away, seed=95,
            action_config=ActionConfig(interval_seconds=1, shot_probability=1),
            defense_config=DefenseConfig(enabled=False), cross_config=CrossConfig(enabled=False),
            shot_config=ShotConfig(enabled=False))
        match.start()
        match.substitute("h", "h-9", "h-18")
        match.substitute("a", "a-1", "a-12")
        match.set_possession("h", "h-18", location=Location(.8, .5))
        match.step()
        event = next(e for e in match.events if e.goal_probability is not None)
        self.assertEqual((event.player_id, event.goalkeeper_id), ("h-18", "a-12"))
        self.assertEqual((event.shooter_finishing, event.goalkeeper_shot_stopping), (.9, .8))

    def test_halftime_management_callback_and_batch_metadata(self):
        match = self.make_match()
        calls = []
        def changes(current):
            calls.append(current.phase)
            current.substitute("h", "h-8", "h-13")
        run_match(match, on_half_time=changes)
        self.assertEqual(calls, [Phase.HALF_TIME])
        self.assertEqual(match.statistics("h").substitutions, 1)
        self.assertEqual(match.statistics("h").substitution_windows, 0)
        with self.assertRaises(RuntimeError):
            match.substitute("h", "h-7", "h-14")
        result = run_batch(1, substitution_config=SubstitutionConfig(max_substitutions=3))
        self.assertEqual(result["substitution_configuration"]["max_substitutions"], 3)

    def test_limit_validation(self):
        for value in (-1, True, 1.5, float("nan")):
            for field in ("max_substitutions", "max_windows"):
                with self.assertRaises(ValueError):
                    SubstitutionConfig(**{field: value})
