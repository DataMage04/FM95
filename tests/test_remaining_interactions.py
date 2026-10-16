from dataclasses import replace
import unittest
from fm95.players.demo import demo_team
from fm95.match import Match,Phase
from fm95.match.mechanics.actions import ActionConfig
from fm95.match.systems.injuries import InjuryConfig
from fm95.match.spatial.pitch import Location
from fm95.match.mechanics.defending import Pressure
from fm95.match.mechanics.offside import OffsideConfig

class RemainingInteractionTests(unittest.TestCase):
    def make_match(self,screening=False):
        m=Match(demo_team('h','H',include_bench=True),demo_team('a','A',include_bench=True),seed=95,
            action_config=ActionConfig(interval_seconds=1,foul_probability=0),
            injury_config=InjuryConfig(treatment_seconds=2),offside_config=OffsideConfig(screening_enabled=screening))
        m.start();m.set_possession('h','h-6',location=Location(.5,.5));return m
    def test_treatment_clock_starts_after_restart_and_returns_without_ball_change(self):
        m=self.make_match();m.treat_player('h','h-7')
        self.assertIsNone(m.treatment('h','h-7').eligible_at)
        self.assertNotIn('h-7',m.formation('h'))
        self.assertFalse(m.injury_substitution_recommendations('h'))
        with self.assertRaises(RuntimeError):m.return_from_treatment('h','h-7')
        m._play_action()
        eligible=m.treatment('h','h-7').eligible_at
        self.assertEqual(eligible,m.elapsed_seconds+2)
        before=m.condition('h','h-7').seconds_played
        m.step();m.step()
        possession=m.possession;restart=m.pending_restart
        m._process_treatments()
        self.assertIn('h-7',m.formation('h'))
        self.assertIsNone(m.treatment('h','h-7'))
        self.assertEqual(m.possession,possession);self.assertEqual(m.pending_restart,restart)
        self.assertEqual(m.condition('h','h-7').seconds_played,before)
        self.assertIn(m.player_locations('h')['h-7'].y,(0,1))
        self.assertEqual(len(m.injury_history('h','h-7')),1)
    def test_substitution_cancels_return_and_halftime_waives_remaining_minute(self):
        m=self.make_match();m.treat_player('h','h-7');m.substitute('h','h-7','h-15')
        self.assertIsNone(m.treatment('h','h-7'))
        with self.assertRaises(ValueError):m.return_from_treatment('h','h-7')
        m=self.make_match();m.treat_player('h','h-7');m.phase=Phase.HALF_TIME;m.resume()
        self.assertIn('h-7',m.formation('h'));self.assertIsNone(m.injury('h','h-7'))
    def test_dismissed_player_never_returns_and_keeper_is_exempt(self):
        m=self.make_match();m.treat_player('h','h-7');m.issue_card('h','h-7','red');m._process_treatments()
        self.assertNotIn('h-7',m.formation('h'));self.assertIsNone(m.treatment('h','h-7'))
        m=self.make_match();m.treat_player('h','h-1')
        self.assertTrue(m.treatment('h','h-1').exempt)
        self.assertIn('h-1',m.formation('h'));self.assertEqual(sum(p.is_goalkeeper for p in m.active_players('h')),1)
    def screen_setup(self,m):
        for p in m.active_players('a'):m._player_locations[p.id]=Location(.8,.7)
        m._player_locations['a-1']=Location(.95,.5)
        for p in m.active_players('h'):m._player_locations[p.id]=Location(.6,.8)
        m._player_locations['h-9']=Location(.94,.5)
        m.set_possession('h','h-6',location=Location(.7,.5))
    def test_explicit_involvement_requires_offside_position_and_impact(self):
        m=self.make_match();self.screen_setup(m)
        context=m._offside_snapshot(m.possession,m._active_team('h'),m._active_team('a'))
        before=tuple(m.events)
        self.assertFalse(m.report_offside_involvement(context,'h-9',Location(.94,.5),kind='screening',impact=False))
        self.assertEqual(tuple(m.events),before)
        self.assertTrue(m.report_offside_involvement(context,'h-9',Location(.94,.5),kind='obstruction',impact=True))
        self.assertEqual(m.pending_restart.kind,'indirect_free_kick')
        self.assertEqual(m.statistics('h').off_ball_offsides,1)
    def test_geometric_screening_prevents_shot_but_not_distant_offside_presence(self):
        m=self.make_match(screening=True);self.screen_setup(m)
        m._play_shot(m.possession,m._active_team('h'),m._active_team('a'),Pressure(None,None,0))
        self.assertEqual(m.statistics('h').shots,0);self.assertEqual(m.statistics('h').off_ball_offsides,1)
        m=self.make_match(screening=True);self.screen_setup(m);m._player_locations['h-9']=Location(.94,.8)
        m._play_shot(m.possession,m._active_team('h'),m._active_team('a'),Pressure(None,None,0))
        self.assertEqual(m.statistics('h').shots,1)
    def test_validation_is_atomic(self):
        m=self.make_match();before=tuple(m.events)
        with self.assertRaises(ValueError):m.treat_player('h','h-12')
        self.assertEqual(tuple(m.events),before)
        for value in (-1,True,1.5):
            with self.assertRaises(ValueError):InjuryConfig(treatment_seconds=value)
        with self.assertRaises(ValueError):InjuryConfig(temporary_probability=2)
