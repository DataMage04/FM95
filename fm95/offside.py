"""Law 11 for point players and the engine's represented touches/challenges."""

from dataclasses import dataclass
from math import isfinite

from fm95.pitch import Location


@dataclass(frozen=True)
class OffsideConfig:
    enabled: bool = True
    screening_enabled: bool = False
    screening_radius: float = .5
    keeper_screening_distance: float = 5

    def __post_init__(self):
        if type(self.enabled) is not bool or type(self.screening_enabled) is not bool:
            raise ValueError("Offside switches must be boolean.")
        for value in (self.screening_radius,self.keeper_screening_distance):
            if type(value) not in (int,float) or not isfinite(value) or value<0:
                raise ValueError("Screening distances must be finite and nonnegative.")


@dataclass(frozen=True)
class OffsideSnapshot:
    team_id: str
    passer_id: str
    ball_location: Location
    defender_line_x: float
    players: tuple[tuple[str, Location], ...]

    def position(self, player_id):
        return next((point for candidate, point in self.players if candidate == player_id), None)


def snapshot(team_id, passer_id, ball, attackers, defenders, locations, direction):
    """Include all active opponents, regardless of goalkeeper designation.

    Halfway, ball and second-last opponent ties are onside. A tiny numerical
    tolerance prevents mirrored floating-point coordinates breaking equality.
    """
    line = sorted((locations[p.id].x for p in defenders), reverse=direction > 0)[1]
    players = tuple((p.id, locations[p.id]) for p in attackers
                    if p.id != passer_id
                    and (locations[p.id].x-.5)*direction > 1e-9
                    and (locations[p.id].x-ball.x)*direction > 1e-9
                    and (locations[p.id].x-line)*direction > 1e-9)
    return OffsideSnapshot(team_id, passer_id, ball, line, players)


def screening_player(context, shooter, keeper, locations, pitch, config):
    """Optional point-player proxy for clearly obstructing the keeper's view.

    A player must be between keeper and shooter, near the keeper, and inside the
    narrow viewing corridor. Mere offside position elsewhere is never penalised.
    """
    if context is None or not config.screening_enabled:return None
    sx,sy=pitch.metres(shooter);kx,ky=pitch.metres(keeper)
    dx,dy=sx-kx,sy-ky
    length2=dx*dx+dy*dy
    if not length2:return None
    candidates=[]
    for pid,start in context.players:
        if pid not in locations:continue
        point=locations[pid];px,py=pitch.metres(point)
        fraction=((px-kx)*dx+(py-ky)*dy)/length2
        separation=((px-kx-fraction*dx)**2+(py-ky-fraction*dy)**2)**.5
        if 0<fraction<1 and separation<=config.screening_radius and pitch.distance(point,keeper)<=config.keeper_screening_distance:
            candidates.append((pitch.distance(point,keeper),pid))
    return min(candidates)[1] if candidates else None
