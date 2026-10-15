"""Discrete defensive movement and pressure; all behavioral values are provisional."""

from dataclasses import dataclass
from math import isfinite

from fm95.pitch import Direction, Location, Pitch


@dataclass(frozen=True)
class DefenseConfig:
    enabled: bool = True
    movement_speed: float = 4.0
    pressure_radius: float = 12.0
    challenge_radius: float = 2.0
    marking_distance: float = 3.0
    marking_radius: float = 20.0
    press_attempt_probability: float = .25
    press_win_probability: float = .40
    pressure_effect: float = .40

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Defense enabled must be boolean.")
        for name in ("movement_speed", "pressure_radius", "challenge_radius",
                     "marking_distance", "marking_radius"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative.")
        if self.pressure_radius <= 0 or self.challenge_radius > self.pressure_radius:
            raise ValueError("Positive pressure radius must contain challenge radius.")
        for name in ("press_attempt_probability", "press_win_probability", "pressure_effect"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1].")


@dataclass(frozen=True)
class Pressure:
    defender_id: str | None
    distance: float | None
    intensity: float


def move_towards(origin: Location, target: Location, distance: float, pitch: Pitch) -> Location:
    separation = pitch.distance(origin, target)
    fraction = min(1, distance/separation) if separation else 1
    return Location(origin.x+(target.x-origin.x)*fraction, origin.y+(target.y-origin.y)*fraction)


def goal_side(target: Location, defending_direction: Direction,
              distance: float, pitch: Pitch) -> Location:
    # A defender's own goal is opposite their attacking direction.
    return Location(max(0, min(1, target.x-int(defending_direction)*distance/pitch.length)), target.y)


def defensive_targets(defenders, opponents, locations, anchors, carrier_id, ball,
                      direction: Direction, pitch: Pitch, config: DefenseConfig):
    """Nearest outfielder closes down; others mark distinct nearby opponents or hold shape."""
    outfield = [p for p in defenders if not p.is_goalkeeper]
    presser = min(outfield, key=lambda p: pitch.distance(locations[p.id], ball))
    targets = dict(anchors)
    targets[presser.id] = goal_side(ball, direction, min(1, config.challenge_radius/2), pitch)
    available = [p for p in opponents if not p.is_goalkeeper and p.id != carrier_id]
    for player in outfield:
        if player.id == presser.id:
            continue
        if available:
            opponent = min(available, key=lambda p: pitch.distance(anchors[player.id], locations[p.id]))
            if pitch.distance(anchors[player.id], locations[opponent.id]) <= config.marking_radius:
                targets[player.id] = goal_side(locations[opponent.id], direction,
                                               config.marking_distance, pitch)
                available.remove(opponent)
    return targets


def measure_pressure(defenders, locations, ball, pitch: Pitch, config: DefenseConfig) -> Pressure:
    outfield = [p for p in defenders if not p.is_goalkeeper]
    if not config.enabled or not outfield:
        return Pressure(None, None, 0)
    closest = min(outfield, key=lambda p: pitch.distance(locations[p.id], ball))
    distance = pitch.distance(locations[closest.id], ball)
    return Pressure(closest.id, distance, max(0, 1-distance/config.pressure_radius))
