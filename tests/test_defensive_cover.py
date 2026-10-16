from dataclasses import replace
import unittest

from fm95.match.mechanics.defending import DefenseConfig, defensive_targets, goal_side
from fm95.players.demo import demo_team
from fm95.match import Match
from fm95.match.spatial.pitch import Direction, Location, Pitch
from fm95.match.systems.roles import Duty


class DefensiveCoverTests(unittest.TestCase):
    def scenario(self, config=None, duties=None, direction=Direction.LEFT):
        defenders = demo_team('a','Away').lineup[1:5]
        opponents = (demo_team('h','Home').lineup[8], demo_team('h','Home').lineup[6])
        ball = Location(.5,.8)
        locations = {'a-2': Location(.501,.8), 'a-3': Location(.56,.65),
                     'a-4': Location(.59,.66), 'a-5': Location(.8,.3),
                     'h-9': ball, 'h-7': Location(.78,.3)}
        if direction == Direction.RIGHT:
            locations = {pid:point.rotated() for pid,point in locations.items()}
            ball = ball.rotated()
        anchors = {p.id:locations[p.id] for p in defenders}
        targets = defensive_targets(defenders, opponents, locations, anchors, 'h-9',
            ball, direction, Pitch(), config or DefenseConfig(), duties)
        return targets, anchors, locations, ball

    def test_one_presser_one_cover_and_remaining_marker(self):
        targets, anchors, locations, ball = self.scenario()
        self.assertLess(Pitch().distance(targets['a-2'],ball),2)
        self.assertGreater(targets['a-3'].x,ball.x)
        self.assertAlmostEqual(targets['a-3'].y,.65)
        self.assertGreater(targets['a-5'].x,locations['h-7'].x)
        self.assertEqual(targets['a-5'].y,locations['h-7'].y)
        self.assertEqual(targets['a-4'],anchors['a-4'])

    def test_defend_duty_prioritised_within_reach_and_both_ends_mirror(self):
        duties = {'a-4':Duty.DEFEND}
        left, anchors, _, ball = self.scenario(duties=duties)
        self.assertEqual(left['a-3'],anchors['a-3'])
        self.assertAlmostEqual(left['a-4'].y,.65)
        right, _, _, _ = self.scenario(duties=duties,direction=Direction.RIGHT)
        for pid in left:
            self.assertAlmostEqual(right[pid].x,left[pid].rotated().x)
            self.assertAlmostEqual(right[pid].y,left[pid].rotated().y)

    def test_cover_can_be_disabled_or_unreachable(self):
        baseline, _, _, _ = self.scenario(config=DefenseConfig(cover_enabled=False))
        unreachable, _, _, _ = self.scenario(config=DefenseConfig(cover_radius=0))
        self.assertEqual(baseline,unreachable)
        enabled, _, _, _ = self.scenario()
        self.assertNotEqual(enabled['a-3'],baseline['a-3'])
        disabled, anchors, _, _ = self.scenario(config=DefenseConfig(enabled=False))
        self.assertEqual(disabled,anchors)

    def test_empty_and_reduced_teams_and_keeper_exclusion(self):
        pitch = Pitch()
        self.assertEqual(defensive_targets((),(),{},{},'h-9',Location(.5,.5),
                                          Direction.LEFT,pitch,DefenseConfig()),{})
        keeper, defender = demo_team('a','Away').lineup[:2]
        locations = {keeper.id:Location(.95,.5),defender.id:Location(.6,.5)}
        targets = defensive_targets((keeper,defender),(),locations,dict(locations),'h-9',
                                    Location(.5,.5),Direction.LEFT,pitch,DefenseConfig())
        self.assertEqual(targets[keeper.id],locations[keeper.id])
        self.assertLess(pitch.distance(targets[defender.id],Location(.5,.5)),2)
        for direction in Direction:
            for point in (Location(0,0),Location(1,1)):
                target = goal_side(point,direction,100,pitch)
                self.assertTrue(0 <= target.x <= 1 and 0 <= target.y <= 1)

    def test_live_cover_uses_actual_elapsed_movement_and_fatigue_accounting(self):
        match = Match(demo_team('h','Home'),demo_team('a','Away'),seed=95)
        match.start()
        match.set_possession('h','h-9',location=Location(.7,.5))
        match.set_player_duty('a','a-3',Duty.DEFEND)
        original = match.player_locations('a')
        ball, events = match.possession, tuple(match.events)
        match._action_elapsed_seconds = 1
        match._update_defensive_positions(match._active_team('h'),match._active_team('a'))
        for pid,point in match.player_locations('a').items():
            distance = match.pitch.distance(original[pid],point)
            self.assertLessEqual(distance,4.000001)
            self.assertAlmostEqual(match.condition('a',pid).distance_covered,distance)
        self.assertEqual(match.possession,ball)
        self.assertEqual(tuple(match.events),events)
        match.issue_card('a','a-3','red')
        match._update_defensive_positions(match._active_team('h'),match._active_team('a'))
        self.assertNotIn('a-3',match.player_locations('a'))

    def test_validation(self):
        for key in ('cover_distance','cover_radius'):
            for value in (-1,True,float('nan'),float('inf'),'near'):
                with self.assertRaises(ValueError):
                    replace(DefenseConfig(),**{key:value})
        for value in (0,1,None,'yes'):
            with self.assertRaises(ValueError):
                DefenseConfig(cover_enabled=value)
