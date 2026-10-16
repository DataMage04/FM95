"""Player-level action tendencies, kept separate from execution attributes."""
from dataclasses import dataclass, fields, replace
from math import isfinite

from fm95.match.mechanics.actions import ActionConfig, adjust_probability


@dataclass(frozen=True)
class DecisionTendencies:
    """How often a player prefers an option when the match situation permits it.

    These are not skill ratings: a shot preference selects shots, while finishing
    and shot-stopping still determine what happens once the shot is taken.
    """
    shooting: float = .5
    dribbling: float = .5
    crossing: float = .5
    through_balls: float = .5
    passing_directness: float = .5
    pressing: float = .5

    def __post_init__(self):
        for item in fields(self):
            value = getattr(self, item.name)
            if (type(value) not in (int, float) or not isfinite(value)
                    or not 0 <= value <= 1):
                raise ValueError(f"Decision tendency {item.name} must be finite and in [0, 1].")


@dataclass(frozen=True)
class DecisionConfig:
    tendency_strength: float = .5

    def __post_init__(self):
        value = self.tendency_strength
        if (type(value) not in (int, float) or not isfinite(value)
                or not 0 <= value <= 1):
            raise ValueError("Decision tendency strength must be finite and in [0, 1].")


def apply_decisions(actions: ActionConfig, cross_probability: float,
                    through_probability: float, team_directness: float,
                    tendencies: DecisionTendencies, config: DecisionConfig):
    """Combine individual preferences with team instructions, without skill changes.

    Probability preferences use smooth odds adjustment. Directness adds a bounded
    instruction offset to destination selection. Neutral tendencies are an identity.
    """
    if not isinstance(actions, ActionConfig) or not isinstance(tendencies, DecisionTendencies):
        raise ValueError("Decision application needs action settings and player tendencies.")
    if not isinstance(config, DecisionConfig):
        raise ValueError("Decision application needs a DecisionConfig.")
    for value in (cross_probability, through_probability, team_directness):
        if (type(value) not in (int, float) or not isfinite(value)
                or not 0 <= value <= 1):
            raise ValueError("Team choice values must be finite and in [0, 1].")
    strength = config.tendency_strength

    adjusted_actions = replace(actions,
        shot_probability=decision_probability(actions.shot_probability, tendencies.shooting, config),
        dribble_probability=decision_probability(actions.dribble_probability, tendencies.dribbling, config))
    cross = decision_probability(cross_probability, tendencies.crossing, config)
    through = decision_probability(through_probability, tendencies.through_balls, config)
    directness = max(0.0, min(1.0, team_directness + strength*(tendencies.passing_directness-.5)))
    return adjusted_actions, cross, through, directness


def decision_probability(base: float, tendency: float, config: DecisionConfig) -> float:
    """Bias an option's probability while leaving its execution result untouched."""
    if (type(base) not in (int, float) or not isfinite(base) or not 0 <= base <= 1
            or type(tendency) not in (int, float) or not isfinite(tendency)
            or not 0 <= tendency <= 1 or not isinstance(config, DecisionConfig)):
        raise ValueError("Decision probability needs bounded values and a DecisionConfig.")
    multiplier = 2 ** (2 * config.tendency_strength * (tendency-.5))
    return adjust_probability(base, multiplier, 1)
