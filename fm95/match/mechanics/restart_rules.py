"""Restart touch restrictions (IFAB Laws 8, 13, 15, 16 and 17).

Handball, accidental penalty double touches, retakes and disciplinary exceptions
are not represented by this ordinary-foot-touch foundation.
"""
from dataclasses import dataclass

from fm95.match.spatial.pitch import Location


@dataclass(frozen=True)
class RestartContext:
    kind: str
    team_id: str
    taker_id: str

    def permits_direct_goal(self, scoring_team_id):
        return (scoring_team_id == self.team_id
                and self.kind not in ('throw_in', 'indirect_free_kick', 'dropped_ball'))


def indirect_location(point, defending_direction, pitch):
    """Attacking indirect kicks inside a goal area move to its parallel line.

    Goal-area dimensions scale with the model's penalty-area depth, as its
    existing goal-kick placement does. On a standard pitch this depth is 5.5 m.
    """
    depth = pitch.penalty_depth/3
    own_x = 0 if int(defending_direction) == 1 else 1
    if (abs(point.x-own_x)*pitch.length < depth
            and abs(point.y-.5)*pitch.width < pitch.goal_width/2+depth):
        return Location(depth/pitch.length if own_x == 0 else 1-depth/pitch.length,point.y)
    return point
