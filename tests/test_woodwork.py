import unittest
from dataclasses import replace
from fm95.players.demo import demo_team
from fm95.match import Match,Phase
from fm95.match.mechanics.actions import ActionConfig
from fm95.match.mechanics.defending import DefenseConfig,Pressure
from fm95.match.mechanics.shooting import ShotConfig
from fm95.match.spatial.pitch import Location
from fm95.match.mechanics.woodwork import WoodworkConfig

class WoodworkTests(unittest.TestCase):
    def test_contact_goal_or_rebound_at_both_ends(self):
        for second in (False,True):
            for goal in (0,1):
                m=Match(demo_team('h','H'),demo_team('a','A'),seed=95,
                    woodwork_config=WoodworkConfig(enabled=True,contact_probability=1,goal_after_contact_probability=goal),
                    action_config=ActionConfig(on_target_probability=0),shot_config=ShotConfig(enabled=False),
                    defense_config=DefenseConfig(enabled=False))
                m.start()
                if second:m.phase=Phase.HALF_TIME;m.resume()
                m.set_possession('h','h-9',location=Location(.8 if not second else .2,.5))
                m._play_shot(m.possession,m._active_team('h'),m._active_team('a'),Pressure(None,None,0))
                stats=m.statistics('h')
                self.assertEqual(stats.woodwork_contacts,1)
                self.assertEqual(stats.shots,1)
                self.assertEqual(stats.goals,goal)
                self.assertEqual(stats.expected_goals,goal)
                self.assertEqual(stats.shots_on_target,goal)
                if not goal:self.assertEqual(m.loose_ball.reason,'woodwork_rebound')
    def test_validation(self):
        for key in ('contact_probability','goal_after_contact_probability'):
            for value in (-1,True,float('nan'),2):
                with self.assertRaises(ValueError):replace(WoodworkConfig(),**{key:value})
        with self.assertRaises(ValueError):WoodworkConfig(rebound_distance=-1)
