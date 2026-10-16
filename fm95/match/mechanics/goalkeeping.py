"""Keeper intervention on aerial deliveries; provisional movement and handling."""

from dataclasses import dataclass
from math import cos, sin, pi, isfinite

from fm95.match.mechanics.actions import adjust_probability
from fm95.players.attributes import ability_multiplier


@dataclass(frozen=True)
class KeeperCrossConfig:
    enabled: bool = True
    attempt_probability: float = .40
    success_probability: float = .70
    claim_probability: float = .60
    intervention_radius: float = 14.0
    movement_speed: float = 4.0
    contact_radius: float = 1.5
    punch_distance: float = 15.0

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Keeper crossing enabled must be boolean.")
        for name in ("attempt_probability", "success_probability", "claim_probability"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1].")
        for name in ("intervention_radius", "movement_speed", "contact_radius", "punch_distance"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative.")


def handling_chance(base: float, handling: float, strength: float) -> float:
    return adjust_probability(base, ability_multiplier(handling-.5, strength), 1)


def keeper_can_intervene(keeper_point, ball_point, direction, pitch, interval, config) -> bool:
    if not config.enabled or not pitch.in_penalty_area(ball_point, direction):
        return False
    distance = pitch.distance(keeper_point, ball_point)
    return (distance <= config.intervention_radius+1e-9
            and distance <= config.movement_speed*interval+config.contact_radius+1e-9)


def punch_endpoint(point, direction, pitch, rng, distance) -> tuple[float, float]:
    angle = (rng.random()-.5)*2*pi/3
    reach = distance*(.5+.5*rng.random())
    return point.x+int(direction)*reach*cos(angle)/pitch.length, point.y+reach*sin(angle)/pitch.width
