"""Synthetic equal-ability teams for examples, not a real player database."""

from fm95.match import Player, Team
from fm95.attributes import Attributes
from fm95.positions import Position


FORMATION_433 = (Position.GK, Position.RB, Position.CB, Position.CB, Position.LB,
                 Position.DM, Position.CM, Position.CM, Position.ST, Position.RW, Position.LW)


def demo_team(team_id: str, name: str, *, attributes: Attributes | None = None) -> Team:
    attributes = attributes if attributes is not None else Attributes()
    return Team(team_id, name, tuple(
        Player(f"{team_id}-{n}", f"{name} Player {n}", is_goalkeeper=n == 1,
               attributes=attributes, position=position)
        for n, position in enumerate(FORMATION_433, start=1)
    ))
