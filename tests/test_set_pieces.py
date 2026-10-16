from dataclasses import replace
from random import Random
import unittest

from fm95.match.mechanics.actions import ActionConfig
from fm95.players.attributes import Attributes
from fm95.match.simulation import run_batch, run_match
from fm95.match.mechanics.boundaries import OutOfPlayConfig
from fm95.match.mechanics.crossing import CrossConfig
from fm95.match.mechanics.defending import DefenseConfig
from fm95.players.demo import demo_team
from fm95.match import Match, Phase, Team
from fm95.match.spatial.pitch import Direction, Location, Pitch
from fm95.match.mechanics.set_pieces import SetPieceConfig, can_shoot_free_kick, penalty_mark, resolve_set_piece
from fm95.match.mechanics.shooting import ShotConfig
from fm95.match.mechanics.through_balls import ThroughBallConfig


class SetPieceTests(unittest.TestCase):
    def make_match(self, **config):
        home = demo_team("h", "Home")
        home = Team(home.id, home.name, tuple(
            replace(p, attributes=Attributes(penalties=.9, free_kicks=.8)) if p.id == "h-10"
            else p for p in home.lineup))
        match = Match(home, demo_team("a", "Away"), seed=95,
            action_config=ActionConfig(interval_seconds=1, shot_probability=0, dribble_probability=0,
                                      foul_probability=1, yellow_card_probability=0, straight_red_probability=0),
            defense_config=DefenseConfig(enabled=False), cross_config=CrossConfig(enabled=False),
            through_ball_config=ThroughBallConfig(enabled=False), out_config=OutOfPlayConfig(enabled=True),
            shot_config=ShotConfig(enabled=False), set_piece_config=SetPieceConfig(**config))
        match.start()
        return match

    def foul(self, match, point=Location(.9, .5), team="h"):
        defending = "a" if team == "h" else "h"
        match.set_possession(team, f"{team}-9", location=point)
        match._award_foul(match.possession, match._active_team(team), match._active_team(defending),
                          f"{defending}-3", "take_on")

    def shot(self, match):
        match.step()
        return next(e for e in reversed(match.events) if e.goal_probability is not None)

    def test_penalty_area_lines_both_directions_and_outside_area(self):
        pitch = Pitch()
        edge = Location(1-pitch.penalty_depth/pitch.length, .5)
        side = Location(.9, .5+pitch.penalty_width/2/pitch.width)
        for point, penalty in ((Location(.9, .5), True), (edge, True), (side, True),
                               (Location(edge.x-.001, .5), False), (Location(.9, side.y+.001), False)):
            for team, where in (("h", point), ("a", point.rotated())):
                with self.subTest(team=team, point=where):
                    match = self.make_match()
                    self.foul(match, where, team)
                    self.assertEqual(match.pending_restart.kind, "penalty" if penalty else "free_kick")
                    self.assertEqual(match.statistics(team).penalties_awarded, int(penalty))
                    self.assertIsNone(match.possession)

    def test_penalty_mark_and_active_specialist_selection(self):
        match = self.make_match()
        self.foul(match)
        restart = match.pending_restart
        self.assertEqual(restart.taker_id, "h-10")
        self.assertAlmostEqual(match.pitch.distance(restart.location, Location(1, .5)), 11)
        self.assertEqual(match.events[-1].origin_location, Location(.9, .5))
        match.issue_card("h", "h-10", "red")
        self.assertNotEqual(match.pending_restart.taker_id, "h-10")
        self.assertFalse(next(p for p in match.active_players("h")
                              if p.id == match.pending_restart.taker_id).is_goalkeeper)
        self.assertEqual(penalty_mark(Pitch(length=80, width=55), Direction.LEFT).x, 11/80)

    def test_penalty_goal_counts_once_and_kicks_off(self):
        match = self.make_match(penalty_on_target_probability=1, penalty_goal_given_on_target_probability=1)
        self.foul(match)
        event = self.shot(match)
        self.assertEqual((event.kind, event.shot_type, event.player_id), ("goal", "penalty", "h-10"))
        self.assertEqual(event.set_piece_ability, .9)
        self.assertEqual((event.block_probability, event.pressure), (0, 0))
        stats = match.statistics("h")
        self.assertEqual((stats.penalties_awarded, stats.penalties_taken, stats.penalties_scored,
                          stats.goals, stats.shots, stats.shots_on_target, stats.expected_goals), (1, 1, 1, 1, 1, 1, 1))
        self.assertEqual(stats.passes_attempted, 0)
        self.assertEqual(match.possession.team_id, "a")
        self.assertEqual(match.dead_ball_seconds, 1)

    def test_penalty_save_miss_and_parry_use_existing_outcomes(self):
        for outcome, target, parry in (("shot_saved", 1, 0), ("shot_missed", 0, 0), ("shot_parried", 1, 1)):
            with self.subTest(outcome=outcome):
                match = self.make_match(penalty_on_target_probability=target,
                                       penalty_goal_given_on_target_probability=0)
                match.shot_config = ShotConfig(enabled=True, block_probability=1,
                                              parry_probability=parry, rebound_distance=0)
                self.foul(match)
                event = self.shot(match)
                self.assertEqual(event.kind, outcome)
                self.assertEqual(event.block_probability, 0)
                self.assertEqual(match.statistics("h").penalties_scored, 0)
                self.assertEqual(match.statistics("a").penalties_saved, target)
                self.assertEqual(match.statistics("h").penalties_off_target, 1-target)
                if outcome == "shot_missed":
                    self.assertEqual(match.pending_restart.kind, "goal_kick")
                elif outcome == "shot_parried":
                    self.assertIsNotNone(match.loose_ball)
                else:
                    self.assertEqual(match.possession.player_id, "a-1")

    def test_penalty_legal_start_positions_and_no_outfield_block(self):
        match = self.make_match()
        self.foul(match)
        restart = match.pending_restart
        # Inspect positions before shooting changes possession or starts a kickoff.
        from fm95.match import Possession
        match._possession = Possession("h", restart.taker_id, location=restart.location)
        match._position_set_piece(match.possession, match._active_team("h"), match._active_team("a"), penalty=True)
        self.assertEqual(match.player_locations("a")["a-1"], Location(1, .5))
        for team in ("h", "a"):
            for player in match.active_players(team):
                if player.id in (restart.taker_id, "a-1"):
                    continue
                point = match.player_locations(team)[player.id]
                self.assertLess(point.x, restart.location.x)
                self.assertFalse(match.pitch.in_penalty_area(point, Direction.LEFT))
                self.assertGreaterEqual(match.pitch.distance(point, restart.location)+1e-9, 9.15)

    def test_direct_free_kick_shot_and_short_or_indirect_restart(self):
        for point, choice, kind in ((Location(.75, .5), 1, "free_kick"),
                (Location(.75, .5), 0, "free_kick"), (Location(.4, .5), 1, "free_kick"),
                (Location(.75, .5), 1, "indirect_free_kick")):
            match = self.make_match(direct_shot_probability=choice, free_kick_on_target_probability=1,
                                   free_kick_goal_given_on_target_probability=1)
            self.foul(match, point)
            match._pending_restart = replace(match.pending_restart, kind=kind)
            match.step()
            expected = point.x == .75 and choice == 1 and kind == "free_kick"
            shots = [e for e in match.events if e.shot_type == "direct_free_kick"]
            self.assertEqual(len(shots), int(expected))
            if expected:
                self.assertEqual((shots[0].kind, shots[0].player_id, shots[0].set_piece_ability),
                                 ("goal", "h-10", .8))
                self.assertEqual(match.statistics("h").direct_free_kick_goals, 1)
            else:
                self.assertTrue(any(e.kind.startswith("pass_") for e in match.events))

    def test_wall_can_block_a_direct_free_kick(self):
        match = self.make_match(direct_shot_probability=1)
        match.shot_config = ShotConfig(block_probability=1, parry_probability=0, rebound_distance=0)
        self.foul(match, Location(.75, .5))
        event = self.shot(match)
        self.assertEqual(event.kind, "shot_blocked")
        self.assertEqual(event.block_probability, 1)
        self.assertIsNotNone(event.blocking_player_id)
        self.assertEqual(match.statistics("h").direct_free_kick_shots, 1)
        self.assertEqual(match.statistics("a").blocks, 1)
        self.assertIsNotNone(match.loose_ball)

    def test_pending_penalty_resolves_before_both_period_whistles(self):
        for end, phase in ((2700, Phase.HALF_TIME), (5400, Phase.FULL_TIME)):
            for target, conversion in ((1, 1), (0, 0), (1, 0)):
                match = self.make_match(penalty_on_target_probability=target,
                                       penalty_goal_given_on_target_probability=conversion)
                if end == 5400:
                    match.phase = Phase.SECOND_HALF
                    match._ends_switched = True
                match.elapsed_seconds = end-1
                match.action_config = replace(match.action_config, interval_seconds=9999)
                self.foul(match, Location(.9, .5) if end == 2700 else Location(.1, .5))
                self.shot(match)
                self.assertEqual(match.phase, phase)
                self.assertEqual(match.statistics("h").penalties_taken, 1)
                self.assertEqual(match.home_goals, conversion)
                self.assertIsNone(match.pending_restart)
                self.assertIsNone(match.possession)
                self.assertIsNone(match.loose_ball)
                self.assertEqual(match.events[-1].kind, phase.value)
                self.assertFalse(any(e.kind == "kickoff" and e.elapsed_seconds == end for e in match.events))

    def test_abandonment_after_foul_cancels_penalty(self):
        match = self.make_match()
        for player_id in ("a-2", "a-4", "a-5", "a-6"):
            match.issue_card("a", player_id, "red")
        match.action_config = replace(match.action_config, straight_red_probability=1)
        self.foul(match)
        self.assertEqual(match.phase, Phase.ABANDONED)
        self.assertIsNone(match.pending_restart)
        self.assertEqual(match.statistics("h").penalties_awarded, 0)

    def test_geometry_abilities_and_probability_endpoints(self):
        config = SetPieceConfig()
        pitch = Pitch()
        self.assertTrue(can_shoot_free_kick(Location(.75, .5), Direction.RIGHT, pitch, config))
        self.assertFalse(can_shoot_free_kick(Location(.5, .5), Direction.RIGHT, pitch, config))
        for penalty in (False, True):
            def result(ability=.5, keeper=.5, strength=1, point=Location(.75, .5)):
                return resolve_set_piece(point, Direction.RIGHT, pitch, Random(95),
                    ActionConfig(attribute_strength=strength), config, penalty=penalty,
                    ability=ability, shot_stopping=keeper)
            self.assertGreater(result(ability=.9).goal_probability, result().goal_probability)
            self.assertLess(result(keeper=.9).goal_probability, result().goal_probability)
            self.assertEqual(result(ability=.9, strength=0).goal_probability, result(strength=0).goal_probability)
        near = resolve_set_piece(Location(.8, .5), Direction.RIGHT, pitch, Random(95), ActionConfig(),
                                 config, penalty=False, ability=.5, shot_stopping=.5)
        far = resolve_set_piece(Location(.7, .5), Direction.RIGHT, pitch, Random(95), ActionConfig(),
                                config, penalty=False, ability=.5, shot_stopping=.5)
        mirror = resolve_set_piece(Location(.2, .5), Direction.LEFT, pitch, Random(95), ActionConfig(),
                                   config, penalty=False, ability=.5, shot_stopping=.5)
        self.assertGreater(near.goal_probability, far.goal_probability)
        self.assertAlmostEqual(near.goal_probability, mirror.goal_probability)

    def test_validation_and_disabled_mode(self):
        for kwargs in ({"enabled": 1}, {"direct_shot_probability": -1}, {"direct_shot_range": 0},
                       {"penalty_on_target_probability": float("nan")},
                       {"free_kick_goal_given_on_target_probability": True}):
            with self.assertRaises(ValueError):
                SetPieceConfig(**kwargs)
        for field in ("penalties", "free_kicks"):
            for value in (-1, 2, float("nan"), True):
                with self.assertRaises(ValueError):
                    Attributes(**{field: value})
        match = self.make_match(enabled=False)
        self.foul(match)
        self.assertEqual(match.pending_restart.kind, "free_kick")
        match.step()
        self.assertFalse(any(e.shot_type in ("penalty", "direct_free_kick") for e in match.events))

    def test_full_match_stats_and_batch_reproduce(self):
        match = run_match(Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95))
        for own, other in ((match.statistics("h"), match.statistics("a")),
                           (match.statistics("a"), match.statistics("h"))):
            self.assertEqual(own.penalties_taken,
                             own.penalties_scored+own.penalties_off_target+other.penalties_saved)
            self.assertEqual(own.free_kicks_awarded+own.penalties_awarded,
                             own.fouls_suffered+own.indirect_free_kicks_awarded)
            self.assertLessEqual(own.penalties_taken, own.penalties_awarded)
            self.assertLessEqual(own.direct_free_kick_shots, own.free_kicks_taken)
        first = run_batch(2)
        self.assertEqual(first, run_batch(2))
        self.assertTrue(first["set_piece_configuration"]["enabled"])
        disabled = run_batch(1, set_piece_config=SetPieceConfig(enabled=False))
        self.assertTrue(all(s["penalties_taken"] == s["direct_free_kick_shots"] == 0
                            for s in disabled["team_averages"].values()))
