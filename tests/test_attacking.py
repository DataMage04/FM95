import unittest
from dataclasses import replace

from fm95.attacking import AttackConfig, attacking_targets
from fm95.demo import demo_team
from fm95.match import Match
from fm95.pitch import Direction, Location
from fm95.roles import Duty


class AttackingMovementTests(unittest.TestCase):
    def make_match(self, **kwargs):
        return Match(demo_team('h', 'Home'), demo_team('a', 'Away'), seed=95, **kwargs)

    def targets(self, match, ball=Location(.6, .5), config=None, duties=None):
        return attacking_targets(match.active_players('h'), match.player_locations('h'),
            match.formation_reference_locations('h'), 'h-9', ball, Direction.RIGHT,
            match.pitch, duties or {}, config or AttackConfig())

    def test_outlets_are_distinct_behind_ball_and_hold_players_keep_shape(self):
        match = self.make_match()
        anchors = match.formation_reference_locations('h')
        targets = self.targets(match, duties={'h-7': Duty.SUPPORT, 'h-8': Duty.SUPPORT,
                                             'h-6': Duty.DEFEND})
        self.assertLess(targets['h-7'].x, .6)
        self.assertLess(targets['h-8'].x, .6)
        self.assertLess((targets['h-7'].y-.5)*(targets['h-8'].y-.5), 0)
        for pid in ('h-1', 'h-3', 'h-4', 'h-6', 'h-9'):
            self.assertEqual(targets[pid], anchors[pid])
        self.assertEqual(self.targets(match, config=AttackConfig(enabled=False)), anchors)

    def test_attack_duty_runner_advances_and_coordinates_rotate(self):
        match = self.make_match()
        players = match.active_players('h')
        locations = match.player_locations('h')
        anchors = match.formation_reference_locations('h')
        duties = {'h-7': Duty.ATTACK}
        right = self.targets(match, duties=duties)
        self.assertGreater(right['h-7'].x, .6)
        left = attacking_targets(players, {pid:p.rotated() for pid,p in locations.items()},
            {pid:p.rotated() for pid,p in anchors.items()}, 'h-9', Location(.4,.5),
            Direction.LEFT, match.pitch, duties, AttackConfig())
        for pid in right:
            self.assertAlmostEqual(left[pid].x, right[pid].rotated().x)
            self.assertAlmostEqual(left[pid].y, right[pid].rotated().y)

    def test_movement_is_bounded_consumes_workload_and_preserves_ball(self):
        match = self.make_match()
        match.start()
        match.set_possession('h', 'h-9', location=Location(.6,.5))
        match.set_player_duty('h','h-7',Duty.SUPPORT)
        old = match.player_locations('h')
        ball = match.possession
        match._action_elapsed_seconds = 1
        match._update_defensive_positions(match._active_team('h'),match._active_team('a'))
        points = match.player_locations('h')
        self.assertEqual(match.possession, ball)
        for pid in points:
            self.assertLessEqual(match.pitch.distance(old[pid],points[pid]),4.000001)
        self.assertGreater(match.condition('h','h-7').distance_covered,0)

    def test_edges_reduced_teams_and_no_supporters(self):
        match = self.make_match()
        for ball in (Location(0,0), Location(1,1)):
            targets = self.targets(match, ball=ball)
            self.assertTrue(all(0 <= p.x <= 1 and 0 <= p.y <= 1 for p in targets.values()))
        match.start()
        match.issue_card('h','h-7','red')
        self.assertNotIn('h-7',self.targets(match))
        self.assertEqual(self.targets(match,config=AttackConfig(max_supporters=0)),
                         match.formation_reference_locations('h'))

    def test_config_validation(self):
        for name in ('support_distance','support_width','forward_distance'):
            for value in (-1,True,float('nan'),float('inf')):
                with self.assertRaises(ValueError):
                    replace(AttackConfig(),**{name:value})
        for value in (-1,3,11,True,1.5):
            with self.assertRaises(ValueError):
                AttackConfig(max_supporters=value)
        with self.assertRaises(ValueError):
            self.make_match(attack_config={})
