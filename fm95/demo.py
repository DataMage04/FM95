"""Synthetic equal-ability teams for examples, not a real player database."""

from fm95.match import Player, Team
from fm95.attributes import Attributes


def demo_team(team_id: str, name: str, *, attributes: Attributes | None = None) -> Team:
    attributes = attributes if attributes is not None else Attributes()
    return Team(team_id, name, tuple(
        Player(f"{team_id}-{n}", f"{name} Player {n}", is_goalkeeper=n == 1,
               attributes=attributes)
        for n in range(1, 12)
    ))
