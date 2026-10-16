"""Short-lived intent after a turnover; no speed or ability bonuses."""
from dataclasses import dataclass
from math import isfinite

from fm95.pitch import Location
from fm95.positions import Position
from fm95.roles import Duty


@dataclass(frozen=True)
class TransitionConfig:
    enabled: bool = True
    duration_seconds: int = 12
    forward_distance: float = 8
    recovery_weight: float = .5

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Transition enabled must be boolean.")
        if type(self.duration_seconds) is not int or self.duration_seconds <= 0:
            raise ValueError("Transition duration must be a positive integer.")
        if (type(self.forward_distance) not in (int, float)
                or not isfinite(self.forward_distance) or self.forward_distance < 0):
            raise ValueError("Transition distance must be finite and nonnegative.")
        if (type(self.recovery_weight) not in (int, float)
                or not isfinite(self.recovery_weight) or not 0 <= self.recovery_weight <= 1):
            raise ValueError("Recovery weight must be in [0, 1].")


@dataclass(frozen=True)
class Transition:
    winning_team_id: str
    losing_team_id: str
    started_at: int
    location: Location


def transition_targets(attackers, defenders, targets, anchors, locations, carrier_id,
                       ball, direction, pitch, duties, strength, config):
    result = dict(targets)
    for player in attackers:
        if (player.id == carrier_id or player.is_goalkeeper or player.position == Position.CB
                or duties.get(player.id) == Duty.DEFEND):
            continue
        point = targets[player.id]
        result[player.id] = Location(max(.01, min(.99, point.x+int(direction)*
            config.forward_distance*strength/pitch.length)), point.y)
    outfield = [p for p in defenders if not p.is_goalkeeper]
    presser = min(outfield, key=lambda p: pitch.distance(locations[p.id], ball), default=None)
    weight = config.recovery_weight*strength
    for player in outfield:
        if player == presser:
            continue
        point, anchor = targets[player.id], anchors[player.id]
        result[player.id] = Location(point.x+(anchor.x-point.x)*weight,
                                     point.y+(anchor.y-point.y)*weight)
    return result
