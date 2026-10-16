"""Synthetic equal-ability teams for examples, not a real player database."""

from fm95.match import Player, Team
from fm95.players.attributes import Attributes
from fm95.match.spatial.positions import Position


FORMATION_433 = (Position.GK, Position.RB, Position.CB, Position.CB, Position.LB,
                 Position.DM, Position.CM, Position.CM, Position.ST, Position.RW, Position.LW)


def demo_team(team_id: str, name: str, *, attributes: Attributes | None = None,
              include_bench: bool = False) -> Team:
    attributes = attributes if attributes is not None else Attributes()
    bench_positions = (Position.GK, Position.CB, Position.LB, Position.CM, Position.AM, Position.RW, Position.ST)
    bench = tuple(Player(f"{team_id}-{n}", f"{name} Player {n}",
                         is_goalkeeper=position == Position.GK, attributes=attributes, position=position)
                  for n, position in enumerate(bench_positions, start=12)) if include_bench else ()
    return Team(team_id, name, tuple(
        Player(f"{team_id}-{n}", f"{name} Player {n}", is_goalkeeper=n == 1,
               attributes=attributes, position=position)
        for n, position in enumerate(FORMATION_433, start=1)
    ), bench)
