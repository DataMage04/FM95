"""Cross delivery and abstract aerial contests. Values await milestone calibration."""

from dataclasses import dataclass
from math import isfinite

from fm95.match.mechanics.actions import adjust_probability
from fm95.players.attributes import ability_multiplier
from fm95.match.spatial.pitch import Direction, Location, Third


@dataclass(frozen=True)
class CrossConfig:
    enabled: bool = True
    choice_probability: float = .25
    corner_cross_probability: float = .75
    delivery_probability: float = .65
    failed_cross_out_probability: float = .30
    attacking_header_probability: float = .50
    clearance_distance: float = 20.0

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Crossing enabled must be boolean.")
        for name in ("choice_probability", "corner_cross_probability", "delivery_probability",
                     "failed_cross_out_probability", "attacking_header_probability"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1].")
        if (type(self.clearance_distance) not in (int, float)
                or not isfinite(self.clearance_distance) or self.clearance_distance < 0):
            raise ValueError("Clearance distance must be finite and nonnegative.")


def can_cross(location: Location, direction: Direction) -> bool:
    return location.zone.third_for(direction) == Third.ATTACKING and location.zone.lane != 1


def delivery_chance(crossing: float, pressure: float, attribute_strength: float,
                    pressure_effect: float, config: CrossConfig) -> float:
    chance = adjust_probability(config.delivery_probability,
                                ability_multiplier(crossing-.5, attribute_strength), 1)
    return adjust_probability(chance, max(.01, 1-pressure*pressure_effect), 1)


def aerial_chance(attacker_heading: float, defender_heading: float,
                   attribute_strength: float, config: CrossConfig) -> float:
    return adjust_probability(config.attacking_header_probability,
        ability_multiplier(attacker_heading-defender_heading, attribute_strength), 1)
