from dataclasses import replace
import unittest
from unittest.mock import patch

from fm95.match.mechanics.actions import ActionConfig
from fm95.players.decisions import (DecisionConfig, DecisionTendencies, apply_decisions,
                            decision_probability)
from fm95.players.demo import demo_team
from fm95.match import Match, Possession, Restart, Team
from fm95.match.spatial.pitch import Location
from fm95.match.mechanics.defending import Pressure
from fm95.match.spatial.positions import Position


class PlayerDecisionTests(unittest.TestCase):
    def test_neutral_tendencies_preserve_team_choice_probabilities(self):
        actions = ActionConfig()
        self.assertEqual(apply_decisions(actions, .25, .20, .7,
            DecisionTendencies(), DecisionConfig()),
            (actions, .25, .20, .7))

    def test_decisions_change_choices_but_leave_execution_skill_probabilities_alone(self):
        actions = ActionConfig(shot_probability=.25, dribble_probability=.20,
                               completion_probability=.8, dribble_success_probability=.6)
        choices, crossing, through, directness = apply_decisions(actions, .25, .20, .5,
            DecisionTendencies(shooting=1, dribbling=0, crossing=1,
                               through_balls=0, passing_directness=1),
            DecisionConfig(tendency_strength=1))
        self.assertGreater(choices.shot_probability, actions.shot_probability)
        self.assertLess(choices.dribble_probability, actions.dribble_probability)
        self.assertGreater(crossing, .25)
        self.assertLess(through, .20)
        self.assertGreater(directness, .5)
        self.assertEqual(choices.completion_probability, actions.completion_probability)
        self.assertEqual(choices.dribble_success_probability, actions.dribble_success_probability)

    def test_zero_decision_strength_disables_personal_preferences(self):
        actions = ActionConfig()
        result = apply_decisions(actions, .25, .20, .7,
            DecisionTendencies(1, 0, 1, 0, 1), DecisionConfig(0))
        self.assertEqual(result, (actions, .25, .20, .7))

    def test_pressing_tendency_changes_attempt_choice_probability_only(self):
        neutral = decision_probability(.25, .5, DecisionConfig(1))
        aggressive = decision_probability(.25, .95, DecisionConfig(1))
        cautious = decision_probability(.25, .05, DecisionConfig(1))
        self.assertEqual(neutral, .25)
        self.assertGreater(aggressive, neutral)
        self.assertLess(cautious, neutral)
        self.assertEqual(decision_probability(.25, .95, DecisionConfig(0)), .25)

    def test_open_play_uses_carriers_decisions_and_restart_does_not(self):
        base = demo_team("h", "Home")
        starter = next(p for p in base.lineup if p.position == Position.CM)
        special = replace(starter, decisions=DecisionTendencies(shooting=.95, passing_directness=.9))
        team = Team(base.id, base.name, tuple(special if p.id == starter.id else p for p in base.lineup))
        match = Match(team, demo_team("a", "Away"), seed=95,
                      action_config=ActionConfig(shot_probability=.2, dribble_probability=0),
                      decision_config=DecisionConfig(1))
        match.start()
        match.set_possession("h", special.id, location=Location(.5, .5))
        with patch("fm95.match.engine.apply_decisions", wraps=apply_decisions) as applied:
            match._resolve_action()
        self.assertEqual(applied.call_count, 1)
        self.assertEqual(applied.call_args.args[4], special.decisions)
        context = next(e for e in match.events if e.kind == "player_decision")
        self.assertEqual(context.decision_tendencies, special.decisions)
        self.assertGreater(context.shot_choice_probability, 0)
        self.assertGreater(context.pass_directness, .5)

        match._pending_restart = Restart("throw_in", "h", special.id,
                                         Location(.5, .5).zone, Location(.5, .5))
        with patch("fm95.match.engine.apply_decisions", wraps=apply_decisions) as applied:
            match._resolve_action()
        self.assertEqual(applied.call_count, 0)

    def test_substitution_carries_the_incoming_players_own_decision_profile(self):
        from fm95.match.systems.substitutions import SubstitutionConfig
        from fm95.players.factory import generate_team

        team = generate_team("h", "Home", seed=95)
        match = Match(team, demo_team("a", "Away"), seed=95,
                      substitution_config=SubstitutionConfig())
        match.start()
        outgoing = next(p for p in match.active_players("h") if p.position == Position.CM)
        incoming = next(p for p in match.available_substitutes("h") if p.position == Position.CM)
        match.substitute("h", outgoing.id, incoming.id)
        active = next(p for p in match.active_players("h") if p.id == incoming.id)
        self.assertEqual(active.decisions, incoming.decisions)
        self.assertNotEqual(active.decisions, outgoing.decisions)

    def test_defender_profile_controls_press_attempt_and_is_logged(self):
        home = demo_team("h", "Home")
        base_away = demo_team("a", "Away")
        defender = next(p for p in base_away.lineup if p.position == Position.CB)
        specialized = replace(defender, decisions=DecisionTendencies(pressing=.95))
        away = Team(base_away.id, base_away.name,
                    tuple(specialized if p.id == defender.id else p for p in base_away.lineup))
        match = Match(home, away, seed=95, decision_config=DecisionConfig(1),
                      action_config=ActionConfig(foul_probability=0))
        carrier = next(p for p in home.lineup if p.position == Position.ST)
        match.start()
        match._rng.random = lambda: 0
        stopped, attempted = match._try_press(
            Possession(home.id, carrier.id, location=Location(.5, .5)), home, away,
            Pressure(defender.id, 0, 1))
        self.assertTrue(stopped)
        self.assertTrue(attempted)
        event = next(e for e in match.events if e.kind.startswith("press_"))
        self.assertGreater(event.press_choice_probability, match.defense_config.press_attempt_probability)

    def test_decision_values_and_strength_are_validated(self):
        for kwargs in ({"shooting": -0.1}, {"through_balls": 1.1},
                       {"crossing": float("nan")}, {"pressing": 1.1}):
            with self.assertRaises(ValueError):
                DecisionTendencies(**kwargs)
        for value in (-.1, 1.1, float("inf")):
            with self.assertRaises(ValueError):
                DecisionConfig(value)


if __name__ == "__main__":
    unittest.main()
