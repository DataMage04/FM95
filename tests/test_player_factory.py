import unittest
from statistics import mean

from fm95.batch import run_batch
from fm95.match import Match
from fm95.player_factory import generate_attributes, generate_team
from fm95.positions import Position


class PlayerFactoryTests(unittest.TestCase):
    def test_generated_squad_is_complete_immutable_and_reproducible(self):
        first = generate_team("h", "Home", seed=95)
        second = generate_team("h", "Home", seed=95)
        self.assertEqual(first, second)
        self.assertEqual(tuple(p.decisions for p in first.squad), tuple(p.decisions for p in second.squad))
        self.assertEqual((len(first.lineup), len(first.bench)), (11, 7))
        self.assertEqual(len({p.id for p in first.squad}), 18)
        self.assertEqual(sum(p.is_goalkeeper for p in first.lineup), 1)
        match = Match(first, generate_team("a", "Away", seed=95))
        self.assertEqual(len(match.active_players("h")), 11)
        self.assertEqual(first, second)

    def test_position_templates_specialize_execution_skills(self):
        keeper = generate_attributes(seed=20, player_id="p", position=Position.GK)
        striker = generate_attributes(seed=20, player_id="p", position=Position.ST)
        self.assertGreater(keeper.shot_stopping, striker.shot_stopping)
        self.assertGreater(keeper.handling, striker.handling)
        self.assertGreater(striker.finishing, keeper.finishing)
        self.assertGreater(striker.heading, keeper.heading)
        keeper_decision = generate_team("g", "Keeper", seed=20).lineup[0].decisions
        striker_decision = next(p.decisions for p in generate_team("s", "Striker", seed=20).lineup
                                if p.position == Position.ST)
        self.assertLess(keeper_decision.shooting, striker_decision.shooting)
        self.assertLess(keeper_decision.dribbling, striker_decision.dribbling)
        defender_decision = next(p.decisions for p in generate_team("d", "Defender", seed=20).lineup
                                 if p.position == Position.CB)
        self.assertGreater(defender_decision.pressing, keeper_decision.pressing)

    def test_team_strength_changes_squad_skill_mean_without_overall_rating(self):
        weak = generate_team("w", "Weak", seed=19, team_strength=.2)
        strong = generate_team("s", "Strong", seed=19, team_strength=.8)
        weak_mean = mean(p.attributes.passing for p in weak.squad)
        strong_mean = mean(p.attributes.passing for p in strong.squad)
        self.assertGreater(strong_mean, weak_mean+.15)
        self.assertFalse(hasattr(strong, "overall"))
        self.assertTrue(all(0 <= value <= 1 for p in strong.squad
                            for value in p.attributes.__dict__.values()))

    def test_invalid_generator_controls_are_rejected(self):
        for kwargs in ({"seed": True}, {"seed": 1, "team_strength": 1.1},
                       {"seed": 1, "team_strength": False}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                generate_attributes(player_id="p", position=Position.CM, **kwargs)

    def test_batch_exposes_synthetic_strength_controls(self):
        result = run_batch(matches=1, seed=90, generated_squads=True,
                           home_strength=.7, away_strength=.3)
        self.assertEqual(result["squad_generation"], {
            "enabled": True, "home_strength": .7, "away_strength": .3, "seed": 90})


if __name__ == "__main__":
    unittest.main()
