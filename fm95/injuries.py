"""Match-ending injury incidents and provisional opt-in exposure probabilities."""

from dataclasses import dataclass
from math import isfinite

from fm95.actions import adjust_probability
from fm95.attributes import ability_multiplier
from fm95.pitch import Location
from fm95.positions import Position


@dataclass(frozen=True)
class InjuryConfig:
    enabled: bool = False
    probability_per_second: float = .000005
    foul_injury_probability: float = .05
    fatigue_risk_strength: float = 1.0

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Injuries enabled must be boolean.")
        for name in ("probability_per_second", "foul_injury_probability"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1].")
        value = self.fatigue_risk_strength
        if type(value) not in (int, float) or not isfinite(value) or value < 0:
            raise ValueError("Fatigue risk strength must be finite and nonnegative.")


@dataclass(frozen=True)
class Injury:
    elapsed_seconds: int
    reason: str
    location: Location
    position: Position


def interval_chance(seconds, proneness, energy, attribute_strength, config):
    """Open-play interval hazard; the match samples at most one incident per action."""
    base = 1-(1-config.probability_per_second)**seconds
    return injury_chance(base, proneness, energy, attribute_strength, config)


def injury_chance(base, proneness, energy, attribute_strength, config):
    odds = ability_multiplier(proneness-.5, attribute_strength)*(1+config.fatigue_risk_strength*(1-energy))
    return adjust_probability(base, odds, 1)
