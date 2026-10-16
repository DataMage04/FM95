import unittest
from dataclasses import replace

from fm95.players.demo import demo_team
from fm95.match import Match, Phase, Restart
from fm95.match.spatial.pitch import Direction, Location, Pitch
from fm95.match.systems.restart_positions import clear_distance, restart_positions


class RestartPositionTests(unittest.TestCase):
    def make_match(self):
        return Match(demo_team('h','Home'),demo_team('a','Away'),seed=95)

    def test_kickoff_own_halves_clearance_switching_and_no_workload_cost(self):
        match = self.make_match()
        original = match.conditions('h')
        match.start()
        for second_half in (False,True):
            if second_half:
                match.phase = Phase.HALF_TIME
                match.resume()
            carrier = match.possession.player_id
            for team in ('h','a'):
                direction = match.attacking_direction(team)
                for pid,p in match.player_locations(team).items():
                    if pid != carrier:
                        self.assertLessEqual((p.x-.5)*int(direction),1e-12)
                    if team != match.possession.team_id:
                        self.assertGreaterEqual(match.pitch.distance(p,Location(.5,.5)),9.15-1e-8)
            self.assertEqual(match.restart_position_violations(),())
        self.assertEqual(match.conditions('h'),original)

    def test_throw_corner_drop_clearances_and_pitch_bounds(self):
        match = self.make_match()
        attackers,defenders = match.home.lineup,match.away.lineup
        for kind,ball,radius in (('throw_in',Location(.5,0),2),('corner',Location(1,1),10.15),
                                  ('dropped_ball',Location(.5,.5),4)):
            locations = {p.id:ball for p in attackers+defenders}
            targets = restart_positions(kind,attackers,defenders,locations,'h-9',ball,
                                        Direction.RIGHT,match.pitch)
            for player in (attackers+defenders if kind=='dropped_ball' else defenders):
                if player.id != 'h-9':
                    self.assertGreaterEqual(match.pitch.distance(targets[player.id],ball),radius-1e-8)
            self.assertEqual(targets['h-9'],ball)
            self.assertTrue(all(0 <= p.x <= 1 and 0 <= p.y <= 1 for p in targets.values()))
            again = restart_positions(kind,attackers,defenders,targets,'h-9',ball,Direction.RIGHT,match.pitch)
            self.assertEqual(targets,again)
            self.assertEqual(locations,{p.id:ball for p in attackers+defenders})

    def test_goal_kick_and_defensive_free_kick_clear_own_penalty_area(self):
        match = self.make_match()
        for direction in Direction:
            for kind in ('goal_kick','free_kick','indirect_free_kick'):
                ball = Location(.05,.5) if direction==Direction.RIGHT else Location(.95,.5)
                locations = {p.id:ball for p in match.home.lineup+match.away.lineup}
                targets = restart_positions(kind,match.home.lineup,match.away.lineup,locations,
                                            'h-1',ball,direction,match.pitch)
                for p in match.away.lineup:
                    self.assertFalse(match.pitch.in_penalty_area(targets[p.id],direction))
                    if kind!='goal_kick':
                        self.assertGreaterEqual(match.pitch.distance(targets[p.id],ball),9.15-1e-8)
                self.assertEqual(targets['h-2'],ball)  # Teammates may remain in their area.

    def test_free_kick_clearance_preserves_goal_line_exception(self):
        match = self.make_match()
        ball = Location(.97,.5)
        locations = {p.id:ball for p in match.home.lineup+match.away.lineup}
        locations['a-1'] = Location(1,.5)
        targets = restart_positions('indirect_free_kick',match.home.lineup,match.away.lineup,
                                    locations,'h-9',ball,Direction.RIGHT,match.pitch)
        self.assertEqual(targets['a-1'],Location(1,.5))
        for player in match.away.lineup[1:]:
            self.assertGreaterEqual(match.pitch.distance(targets[player.id],ball),9.15-1e-8)

    def test_pending_restart_correction_is_auditable_and_preserves_ball_and_conditions(self):
        match = self.make_match()
        match.start()
        ball = Location(.4,0)
        match._possession = None
        match._pending_restart = Restart('throw_in','h','h-7',ball.zone,ball)
        match._player_locations['a-7'] = ball
        conditions,events = match.conditions('a'),tuple(match.events)
        pending = match.pending_restart
        self.assertIn('a-7',match.restart_position_violations())
        match._position_restart()
        self.assertEqual(match.restart_position_violations(),())
        self.assertEqual(match.pending_restart,pending)
        self.assertEqual(match.ball_location,ball)
        self.assertEqual(match.conditions('a'),conditions)
        self.assertEqual(tuple(match.events),events)
        match.issue_card('a','a-7','red')
        self.assertNotIn('a-7',match._restart_position_targets())
        match._position_restart()

    def test_clearance_projects_safely_at_all_edges(self):
        pitch = Pitch()
        for ball in (Location(0,0),Location(1,1),Location(0,.5),Location(.5,1)):
            point = clear_distance(ball,ball,9.15,pitch,Direction.RIGHT)
            self.assertGreaterEqual(pitch.distance(point,ball),9.15-1e-8)
            self.assertEqual(clear_distance(point,ball,9.15,pitch,Direction.RIGHT),point)
        match = self.make_match()
        with self.assertRaises(RuntimeError):
            match.restart_position_violations()
