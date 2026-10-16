import unittest
from unittest.mock import patch

from fm95.demo import demo_team
from fm95.match import Match, Phase
from fm95.pitch import Location
from fm95.positions import Position
from fm95.roles import Duty, instructions_for
from fm95.tactics import TeamTactics, action_preferences
from fm95.actions import ActionConfig


class FormationAndDutyTests(unittest.TestCase):
    def make_match(self):
        return Match(demo_team('h', 'Home', include_bench=True),
                     demo_team('a', 'Away', include_bench=True), seed=95)

    def test_live_assignment_preserves_natural_position_ball_and_actual_points(self):
        match = self.make_match()
        match.start()
        assignments = match.formation('h')
        assignments['h-6'] = Position.AM
        before = (match.possession, match.player_locations('h'), match._seconds_since_action)
        match.set_formation('h', assignments)
        self.assertEqual(before, (match.possession, match.player_locations('h'), match._seconds_since_action))
        self.assertEqual(match.home.lineup[5].position, Position.DM)
        self.assertEqual(match.formation('h')['h-6'], Position.AM)
        self.assertEqual(match.events[-1].kind, 'formation_changed')
        assignments.clear()
        self.assertEqual(len(match.formation('h')), 11)

    def test_invalid_assignment_is_atomic_and_cannot_restore_dismissed_players(self):
        match = self.make_match()
        match.start()
        original = match.formation('h')
        bad = dict(original, **{'h-2': Position.GK})
        for assignments in (bad, {'h-1': Position.GK}, dict(original, **{'h-2': 'CB'})):
            events = tuple(match.events)
            with self.assertRaises(ValueError):
                match.set_formation('h', assignments)
            self.assertEqual(match.formation('h'), original)
            self.assertEqual(tuple(match.events), events)
        match.issue_card('h', 'h-2', 'red')
        with self.assertRaises(ValueError):
            match.set_formation('h', original)
        reduced = match.formation('h')
        reduced['h-6'] = Position.CB
        match.set_formation('h', reduced)
        self.assertEqual(len(match.active_players('h')), 10)

    def test_duties_change_targets_in_direction_of_attack_without_teleporting(self):
        match = self.make_match()
        for team in ('h', 'a'):
            pid = team+'-7'
            before = match.formation_reference_locations(team)[pid]
            actual = match.player_locations(team)
            match.set_player_duty(team, pid, Duty.ATTACK)
            after = match.formation_reference_locations(team)[pid]
            self.assertGreater((after.x-before.x)*int(match.attacking_direction(team)), 0)
            self.assertEqual(match.player_locations(team), actual)
        match.start()
        match.phase = Phase.HALF_TIME
        match.resume()
        self.assertLess(match.formation_reference_locations('h')['h-7'].x, .5)

    def test_duty_preferences_change_choices_without_ability_boosts(self):
        match = self.make_match()
        attrs = match.effective_attributes('h', 'h-9')
        match.set_player_duty('h', 'h-9', Duty.ATTACK)
        attack = action_preferences(ActionConfig(), instructions_for(TeamTactics(), Duty.ATTACK))
        defend = action_preferences(ActionConfig(), instructions_for(TeamTactics(), Duty.DEFEND))
        self.assertGreater(attack.shot_probability, defend.shot_probability)
        self.assertGreater(attack.dribble_probability, defend.dribble_probability)
        self.assertEqual(attrs, match.effective_attributes('h', 'h-9'))
        match.start()
        match.set_possession('h', 'h-9', location=Location(.8, .5))
        with patch('fm95.match.action_preferences', wraps=action_preferences) as choices:
            match._play_action()
        self.assertEqual(choices.call_args.args[1], instructions_for(TeamTactics(), Duty.ATTACK))

    def test_substitute_inherits_assignment_and_duty(self):
        match = self.make_match()
        positions = match.formation('h')
        positions['h-7'] = Position.AM
        match.set_formation('h', positions)
        match.set_player_duty('h', 'h-7', Duty.SUPPORT)
        match.start()
        match.substitute('h', 'h-7', 'h-15')
        self.assertEqual(match.formation('h')['h-15'], Position.AM)
        self.assertEqual(match.player_duty('h', 'h-15'), Duty.SUPPORT)
        self.assertEqual(match.home.bench[3].position, Position.CM)

    def test_keeper_injury_and_replacement_preserve_valid_formation(self):
        match = self.make_match()
        match.start()
        match.set_player_duty('h', 'h-2', Duty.ATTACK)
        match.injure_player('h', 'h-1')
        assignments = match.formation('h')
        assignments['h-6'] = Position.CB
        match.set_formation('h', assignments)
        match.substitute('h', 'h-1', 'h-12')
        self.assertEqual(sum(p.is_goalkeeper for p in match.active_players('h')), 1)
        self.assertEqual(match.formation('h')['h-2'], Position.RB)
        self.assertEqual(match.player_duty('h', 'h-12'), Duty.BALANCED)

    def test_validation_and_terminal_phase(self):
        match = self.make_match()
        for pid, duty in [('h-1', Duty.ATTACK), ('h-12', Duty.SUPPORT), ('a-7', Duty.DEFEND), ('h-7', 'attack')]:
            with self.assertRaises(ValueError):
                match.set_player_duty('h', pid, duty)
        match.phase = Phase.FULL_TIME
        with self.assertRaises(RuntimeError):
            match.set_formation('h', match.formation('h'))
        with self.assertRaises(RuntimeError):
            match.set_player_duty('h', 'h-7', Duty.ATTACK)
