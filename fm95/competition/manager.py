"""Offline manager assignment and deterministic CPU squad preparation."""

from dataclasses import dataclass
from hashlib import sha256

from fm95.match.spatial.positions import Position
from fm95.match.systems.substitution_policy import ROLE_SKILLS, role_ability, suitability
from fm95.match.tactics import TeamTactics
from fm95.teams.club import Club, SquadSelection


@dataclass(frozen=True)
class Manager:
    id: str
    name: str

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id.strip() or not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Manager needs a non-empty ID and name.")


@dataclass(frozen=True)
class ManagerAssignment:
    manager: Manager
    team_id: str
    selection: SquadSelection
    tactics: TeamTactics


def cpu_selection(club: Club, fixture_seed: int) -> SquadSelection:
    """Choose a legal 4-3-3 by role ability; fixture seed breaks exact ties."""
    if type(fixture_seed) is not int:
        raise ValueError("Fixture seed must be an integer.")
    players = list(club.players)
    keepers = [p for p in players if p.is_goalkeeper]
    if not keepers:
        raise ValueError(f"Club {club.id} has no registered goalkeeper.")
    def priority(pid: str) -> bytes:
        return sha256(f"{fixture_seed}:{club.id}:{pid}".encode()).digest()
    keeper = min(keepers, key=lambda p: (-role_ability(p.attributes, Position.GK), priority(p.id), p.id))
    available = [p for p in players if p.id != keeper.id and not p.is_goalkeeper]
    # Preserve the established FM95 4-3-3 position layout.
    roles = (Position.LB, Position.CB, Position.CB, Position.RB, Position.DM,
             Position.CM, Position.CM, Position.ST, Position.RW, Position.LW)
    chosen = [keeper]
    for role in roles:
        eligible = [p for p in available if suitability(role, p.position) > 0]
        if not eligible:
            eligible = available
        if not eligible:
            raise ValueError(f"Club {club.id} cannot fill an 11-player CPU lineup.")
        def score(player):
            fit = suitability(role, player.position) or .25
            return (-(role_ability(player.attributes, role) * fit), priority(player.id), player.id)
        player = min(eligible, key=score)
        chosen.append(player)
        available.remove(player)
    return SquadSelection(tuple(player.id for player in chosen))
