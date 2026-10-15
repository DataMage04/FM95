"""Synthetic equal-ability teams for examples, not a real player database."""

from fm95.match import Player, Team


def demo_team(team_id: str, name: str) -> Team:
    return Team(team_id, name, tuple(
        Player(f"{team_id}-{n}", f"{name} Player {n}", is_goalkeeper=n == 1)
        for n in range(1, 12)
    ))
