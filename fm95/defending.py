"""Discrete defensive movement and pressure; all behavioral values are provisional."""

from dataclasses import dataclass
from math import isfinite

from fm95.pitch import Direction, Location, Pitch
from fm95.roles import Duty


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
    cover_enabled: bool = True
    cover_distance: float = 6.0
    cover_radius: float = 20.0

    def __post_init__(self):
        if type(self.enabled) is not bool or type(self.cover_enabled) is not bool:
            raise ValueError("Defense and cover enabled must be boolean.")
        for name in ("movement_speed", "pressure_radius", "challenge_radius",
                     "marking_distance", "marking_radius", "cover_distance", "cover_radius"):
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
                      direction: Direction, pitch: Pitch, config: DefenseConfig, duties=None):
    """Nearest outfielder presses; a nearby teammate covers the central route.

    With at least three outfielders, reserve one reachable covering player and
    leave the others marking distinct opponents or holding shape. Cover is an
    intent, not an extra challenge or a bonus to tackle/shot probabilities.
    """
    outfield = [p for p in defenders if not p.is_goalkeeper]
    targets = dict(anchors)
    if not config.enabled or not outfield:
        return targets
    duties = duties or {}
    presser = min(outfield, key=lambda p: pitch.distance(locations[p.id], ball))
    targets[presser.id] = goal_side(ball, direction, min(1, config.challenge_radius/2), pitch)
    cover_id = None
    if config.cover_enabled and len(outfield) >= 3:
        point = goal_side(ball, direction, config.cover_distance, pitch)
        point = Location(point.x, .5+(point.y-.5)*.5)
        candidates = [p for p in outfield if p.id != presser.id
                      and pitch.distance(locations[p.id], point) <= config.cover_radius]
        if candidates:
            cover = min(candidates, key=lambda p: (duties.get(p.id) != Duty.DEFEND,
                        pitch.distance(locations[p.id], point), p.id))
            cover_id = cover.id
            targets[cover_id] = point
    available = [p for p in opponents if not p.is_goalkeeper and p.id != carrier_id]
    for player in outfield:
        if player.id in (presser.id, cover_id):
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
