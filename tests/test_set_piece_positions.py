import unittest
from unittest.mock import patch

from fm95.defending import Pressure
from fm95.demo import demo_team
from fm95.match import Match, Phase, Restart
from fm95.pitch import Location
from fm95.set_pieces import penalty_mark
from fm95.set_piece_positions import clear_attacking_wall


class SetPiecePositionTests(unittest.TestCase):
    def make_match(self):
        match = Match(demo_team('h','Home'),demo_team('a','Away'),seed=95)
        match.start()
        return match

    def test_penalty_inspection_and_execution_share_legal_setup_at_both_ends(self):
        for second in (False,True):
            match = self.make_match()
            if second:
                match.phase=Phase.HALF_TIME
                match.resume()
            direction = match.attacking_direction('h')
            ball = penalty_mark(match.pitch,direction)
            match._possession = None
            match._pending_restart = Restart('penalty','h','h-9',ball.zone,ball)
            for pid in match._player_locations:
                match._player_locations[pid] = ball
            before = match.conditions('h'),match.conditions('a'),tuple(match.events)
            self.assertTrue(match.restart_position_violations())
            match._position_restart()
            self.assertEqual(match.restart_position_violations(),())
            for team in ('h','a'):
                for player in match.active_players(team):
                    point=match.player_locations(team)[player.id]
                    if player.id=='h-9':
                        self.assertEqual(point,ball)
                    elif player.id=='a-1':
                        self.assertEqual(point,Location(1 if int(direction)==1 else 0,.5))
                    else:
                        self.assertGreaterEqual(match.pitch.distance(point,ball),9.15-1e-8)
                        self.assertLessEqual((point.x-ball.x)*int(direction),0)
                        self.assertFalse(match.pitch.in_penalty_area(point,-int(direction)))
            self.assertEqual((match.conditions('h'),match.conditions('a'),tuple(match.events)),before)
            with patch.object(match,'_play_shot') as shot:
                match._play_action()
            self.assertEqual(shot.call_args.kwargs['set_piece'],'penalty')

    def test_attacking_players_clear_three_player_wall_at_both_ends(self):
        for second in (False,True):
            match=self.make_match()
            if second:
                match.phase=Phase.HALF_TIME
                match.resume()
            direction=match.attacking_direction('h')
            ball=Location(.78,.5) if int(direction)==1 else Location(.22,.5)
            match.set_possession('h','h-9',location=ball)
            # Put every attacker on the expected wall, forcing a genuine correction.
            centre=Location(ball.x+int(direction)*9.15/match.pitch.length,.5)
            for player in match.active_players('h'):
                if player.id!='h-9':
                    match._player_locations[player.id]=centre
            conditions=match.conditions('h'),match.conditions('a')
            match._position_set_piece(match.possession,match._active_team('h'),match._active_team('a'),penalty=False)
            wall=[p for p in match.active_players('a') if not p.is_goalkeeper
                  and match.pitch.distance(match._player_locations[p.id],ball)<9.3]
            self.assertGreaterEqual(len(wall),3)
            for player in match.active_players('h'):
                for defender in wall:
                    self.assertGreaterEqual(match.pitch.distance(match._player_locations[player.id],
                        match._player_locations[defender.id]),1-1e-8)
            self.assertEqual((match.conditions('h'),match.conditions('a')),conditions)
            self.assertEqual(match.possession.location,ball)

    def test_small_wall_has_no_attacker_spacing_restriction(self):
        match=self.make_match()
        players=match.active_players('h')
        wall=match.active_players('a')[1:3]
        locations=dict(match._player_locations)
        locations['h-7']=locations[wall[0].id]
        self.assertEqual(clear_attacking_wall(players,wall,locations,Location(.8,.5),
                                             match.attacking_direction('h'),match.pitch),locations)

    def test_close_goal_wall_keeps_kicker_clear_and_remains_in_pitch(self):
        match=self.make_match()
        match.set_possession('h','h-9',location=Location(.999,.5))
        match._position_set_piece(match.possession,match._active_team('h'),match._active_team('a'),penalty=False)
        for p in match.active_players('a'):
            point=match._player_locations[p.id]
            self.assertTrue(0<=point.x<=1 and 0<=point.y<=1)
            if not p.is_goalkeeper:
                self.assertGreaterEqual(match.pitch.distance(point,match.possession.location),1-1e-8)
