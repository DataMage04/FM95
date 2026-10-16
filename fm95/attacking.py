"""Coordinated off-ball targets; distances and responses remain provisional."""
from dataclasses import dataclass
from math import isfinite

from fm95.pitch import Location
from fm95.positions import Position
from fm95.roles import Duty


@dataclass(frozen=True)
class AttackConfig:
    enabled: bool = True
    support_distance: float = 12
    support_width: float = 10
    forward_distance: float = 10
    max_supporters: int = 2

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Attack enabled must be boolean.")
        for name in ('support_distance', 'support_width', 'forward_distance'):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative.")
        if type(self.max_supporters) is not int or not 0 <= self.max_supporters <= 2:
            raise ValueError("max_supporters must be an integer in [0, 2].")


def attacking_targets(players, locations, anchors, carrier_id, ball, direction, pitch,
                      duties, config):
    """Offer two staggered outlets and advance designated runners.

    Defend-duty players and balanced centre backs hold their shape. Support-duty
    players take priority for outlets, then distance and ID break ties. Targets
    express intent only: the match applies movement, fatigue and offside normally.
    """
    targets = dict(anchors)
    if not config.enabled:
        return targets
    candidates = [p for p in players if p.id != carrier_id and not p.is_goalkeeper
                  and duties.get(p.id, Duty.BALANCED) != Duty.DEFEND
                  and (p.position != Position.CB or duties.get(p.id) in (Duty.SUPPORT, Duty.ATTACK))]
    supporters = sorted((p for p in candidates if duties.get(p.id) != Duty.ATTACK),
                        key=lambda p: (duties.get(p.id) != Duty.SUPPORT,
                                       pitch.distance(locations[p.id], ball), p.id))[:config.max_supporters]
    # Work in the team's attacking frame so both ends behave identically.
    local_ball = ball if int(direction) == 1 else ball.rotated()
    for index, player in enumerate(supporters):
        anchor = anchors[player.id] if int(direction) == 1 else anchors[player.id].rotated()
        side = -1 if anchor.y < local_ball.y else 1
        if index and side == previous_side:
            side = -side
        previous_side = side
        point = Location(max(.01, min(.99, local_ball.x-config.support_distance/pitch.length)),
                         max(.01, min(.99, local_ball.y+side*config.support_width/pitch.width)))
        targets[player.id] = point if int(direction) == 1 else point.rotated()
    for player in candidates:
        if duties.get(player.id) == Duty.ATTACK:
            anchor = anchors[player.id] if int(direction) == 1 else anchors[player.id].rotated()
            point = Location(min(.99, max(anchor.x, local_ball.x+config.forward_distance/pitch.length)), anchor.y)
            targets[player.id] = point if int(direction) == 1 else point.rotated()
    return targets
