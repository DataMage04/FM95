"""Law 11 for point players and the engine's represented touches/challenges."""

from dataclasses import dataclass

from fm95.pitch import Location


@dataclass(frozen=True)
class OffsideConfig:
    enabled: bool = True

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Offside enabled must be boolean.")


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
