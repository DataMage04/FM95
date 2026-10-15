from dataclasses import replace
import unittest

from fm95.actions import ActionConfig
from fm95.batch import run_match, run_batch
from fm95.boundaries import Boundary, BoundaryExit, OutOfPlayConfig, first_exit
from fm95.defending import DefenseConfig
from fm95.demo import demo_team
from fm95.match import Match, Phase
from fm95.pitch import Location, Pitch
from fm95.shooting import ShotConfig


class BoundaryTests(unittest.TestCase):
    def make_match(self):
        return Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95,
            action_config=ActionConfig(interval_seconds=1, shot_probability=0, dribble_probability=0,
                                      completion_probability=1), defense_config=DefenseConfig(enabled=False))

    def test_segment_first_exit_and_boundary_points(self):
        origin = Location(.5, .5)
        self.assertIsNone(first_exit(origin, 1, .5))
        self.assertIsNone(first_exit(origin, .3, .2))
        right = first_exit(origin, 1.2, .6)
        self.assertEqual(right.boundary, Boundary.RIGHT)
        self.assertEqual(right.location.x, 1)
        self.assertAlmostEqual(right.location.y, .5+.1*.5/.7)
        self.assertEqual(first_exit(origin, -.1, .4).boundary, Boundary.LEFT)
        self.assertEqual(first_exit(origin, .2, -.1).boundary, Boundary.BOTTOM)
        self.assertEqual(first_exit(origin, .8, 1.1).boundary, Boundary.TOP)
        self.assertEqual(first_exit(origin, 1.2, 1.2).boundary, Boundary.TOP)
        self.assertEqual(first_exit(Location(0, .5), -.1, .5).location, Location(0, .5))

    def test_last_touch_routes_all_first_half_goal_line_cases(self):
        for boundary, x, last_team, last_player, kind, winner in (
            (Boundary.LEFT, 0, "h", "h-3", "corner", "a"),
            (Boundary.LEFT, 0, "a", "a-9", "goal_kick", "h"),
            (Boundary.RIGHT, 1, "a", "a-3", "corner", "h"),
            (Boundary.RIGHT, 1, "h", "h-9", "goal_kick", "a"),
        ):
            match = self.make_match()
            match.pitch = Pitch(length=120)
            match.start()
            match.award_out_of_play(BoundaryExit(boundary, Location(x, .2)), last_team, last_player)
            restart = match.pending_restart
            self.assertEqual((restart.kind, restart.team_id), (kind, winner))
            self.assertIsNone(match.possession)
            self.assertIsNone(match.loose_ball)
            if kind == "corner":
                self.assertEqual(restart.location, Location(x, 0))
            else:
                self.assertTrue(next(p for p in match.active_players(winner) if p.id == restart.taker_id).is_goalkeeper)
                self.assertLessEqual(min(restart.location.x, 1-restart.location.x)*match.pitch.length, 5.5)

    def test_throw_in_uses_exit_point_and_opposite_last_touch_team(self):
        match = self.make_match()
        match.start()
        point = Location(.4, 1)
        match.award_out_of_play(BoundaryExit(Boundary.TOP, point), "h", "h-7")
        self.assertEqual((match.pending_restart.kind, match.pending_restart.team_id), ("throw_in", "a"))
        self.assertEqual(match.ball_location, point)
        index = len(match.events)
        match.step()
        self.assertEqual([e.kind for e in match.events[index:]], ["throw_in_taken", "pass_completed"])
        self.assertEqual(match.dead_ball_seconds, 1)
        self.assertIsNone(match.pending_restart)
        self.assertNotEqual(match.events[-1].player_id, match.events[-1].receiver_id)

    def test_end_switching_routes_goal_lines_correctly(self):
        match = self.make_match()
        match.action_config = ActionConfig(interval_seconds=9999)
        match.start()
        for _ in range(2700):
            match.step()
        match.resume()
        match.award_out_of_play(BoundaryExit(Boundary.LEFT, Location(0, .8)), "h", "h-9")
        self.assertEqual((match.pending_restart.kind, match.pending_restart.team_id), ("goal_kick", "a"))

    def test_corner_is_taken_as_short_restart_by_active_outfielder(self):
        match = self.make_match()
        match.start()
        match.award_out_of_play(BoundaryExit(Boundary.RIGHT, Location(1, .8)), "a", "a-3")
        taker = match.pending_restart.taker_id
        self.assertFalse(next(p for p in match.active_players("h") if p.id == taker).is_goalkeeper)
        self.assertEqual(match.pending_restart.location, Location(1, 1))
        match.step()
        self.assertEqual([e.kind for e in match.events[-2:]], ["corner_taken", "pass_completed"])
        self.assertEqual((match.statistics("h").corners_awarded, match.statistics("h").corners_taken), (1, 1))

    def test_blocked_exit_records_deflector_last_touch(self):
        match = self.make_match()
        match.action_config = replace(match.action_config, shot_probability=1,
                                      on_target_probability=1, goal_given_on_target_probability=1)
        match.shot_config = ShotConfig(block_probability=1, rebound_distance=1000)
        match.start()
        match.set_possession("a", "a-3", location=Location(.8, .5))
        match.set_possession("h", "h-9", location=Location(.7, .5))
        match.step()
        out = next(e for e in match.events if e.kind == "ball_out")
        self.assertEqual((out.team_id, out.player_id), ("a", "a-3"))
        self.assertEqual(match.statistics("a").blocks, 1)
        self.assertIsNone(match.loose_ball)

    def test_failed_pass_goes_out_and_keeps_intended_zone_for_probability(self):
        match = self.make_match()
        match.action_config = replace(match.action_config, completion_probability=0)
        match.out_config = OutOfPlayConfig(failed_pass_out_probability=1)
        match.start()
        match.step()
        self.assertEqual(match.events[-3].kind, "pass_out")
        self.assertIsNotNone(match.events[-3].intended_zone)
        self.assertIsNone(match.events[-3].interceptor_id)
        self.assertEqual(match.statistics("h").passes_out, 1)
        self.assertEqual(match.statistics("a").interceptions, 0)
        self.assertIsNotNone(match.pending_restart)

    def test_parried_exit_uses_keeper_as_last_touch(self):
        match = self.make_match()
        match.action_config = replace(match.action_config, shot_probability=1,
                                      on_target_probability=1, goal_given_on_target_probability=0)
        match.shot_config = ShotConfig(block_probability=0, parry_probability=1, rebound_distance=1000)
        match.start()
        match.set_possession("h", "h-9", location=Location(.8, .5))
        match.step()
        out = next(e for e in match.events if e.kind == "ball_out")
        self.assertEqual((out.team_id, out.player_id), ("a", "a-1"))
        self.assertIsNotNone(match.pending_restart)
        self.assertIsNone(match.loose_ball)
        self.assertEqual(match.statistics("a").parries, 1)

    def test_miss_awards_delayed_goal_kick(self):
        match = self.make_match()
        match.action_config = replace(match.action_config, shot_probability=1, on_target_probability=0)
        match.start()
        match.set_possession("h", "h-9", location=Location(.8, .5))
        match.step()
        self.assertEqual(match.pending_restart.kind, "goal_kick")
        self.assertEqual(match.pending_restart.team_id, "a")
        self.assertIsNone(match.possession)
        match.step()
        self.assertEqual(match.events[-2].kind, "goal_kick_taken")

    def test_dismissed_taker_is_replaced_and_whistle_clears_restart(self):
        match = self.make_match()
        match.start()
        match.award_out_of_play(BoundaryExit(Boundary.RIGHT, Location(1, .2)), "h", "h-9")
        match.issue_card("a", "a-1", "red")
        self.assertNotEqual(match.pending_restart.taker_id, "a-1")
        match.step()
        self.assertEqual(match.events[-2].kind, "goal_kick_taken")
        match.action_config = ActionConfig(interval_seconds=9999)
        for _ in range(2699-match.elapsed_seconds):
            match.step()
        match.award_out_of_play(BoundaryExit(Boundary.TOP, Location(.5, 1)), "h", "h-7")
        match.step()
        self.assertEqual(match.phase, Phase.HALF_TIME)
        self.assertIsNone(match.pending_restart)
        self.assertIsNone(match.ball_location)

    def test_full_match_and_batch_time_reconciliation(self):
        matches = [run_match(Match(demo_team("h", "Home"), demo_team("a", "Away"), seed=95)) for _ in range(2)]
        self.assertEqual(matches[0].events, matches[1].events)
        match = matches[0]
        home, away = match.statistics("h"), match.statistics("a")
        self.assertEqual(home.possession_seconds+away.possession_seconds+match.loose_ball_seconds+match.dead_ball_seconds, 5400)
        self.assertGreater(match.dead_ball_seconds, 0)
        for own, other in ((home, away), (away, home)):
            self.assertEqual(own.passes_attempted-own.passes_completed,
                             own.passes_out+own.misplaced_passes+other.interceptions)
            self.assertLessEqual(own.corners_taken, own.corners_awarded)
            self.assertLessEqual(own.throw_ins_taken, own.throw_ins_awarded)
        summary = run_batch(1)
        self.assertEqual(sum(s["possession_seconds"] for s in summary["team_averages"].values())
                         + summary["average_loose_ball_seconds"]+summary["average_dead_ball_seconds"], 5400)

    def test_validation_and_rejected_exit_is_atomic(self):
        for kwargs in ({"enabled":1}, {"failed_pass_out_probability":1.1},
                       {"failed_pass_out_probability":float("nan")}):
            with self.assertRaises(ValueError):
                OutOfPlayConfig(**kwargs)
        with self.assertRaises(ValueError):
            BoundaryExit(Boundary.TOP, Location(.5, .5))
        with self.assertRaises(ValueError):
            first_exit(Location(.5, .5), float("nan"), 1.2)
        match = self.make_match()
        match.start()
        before, count = match.possession, len(match.events)
        with self.assertRaises(ValueError):
            match.award_out_of_play(BoundaryExit(Boundary.TOP, Location(.5, 1)), "h", "a-2")
        self.assertEqual(match.possession, before)
        self.assertEqual(len(match.events), count)
