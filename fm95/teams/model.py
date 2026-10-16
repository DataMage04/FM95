"""A club's match-ready squad."""

from dataclasses import dataclass

from fm95.players.model import Player


@dataclass(frozen=True)
class Team:
    id: str
    name: str
    lineup: tuple[Player, ...]
    bench: tuple[Player, ...] = ()

    @property
    def squad(self) -> tuple[Player, ...]:
        return self.lineup + self.bench

    def __post_init__(self):
        object.__setattr__(self, "lineup", tuple(self.lineup))
        object.__setattr__(self, "bench", tuple(self.bench))
        if any(not isinstance(player, Player) for player in self.squad):
            raise ValueError("A match squad must contain Player instances.")
        if len(self.lineup) != 11:
            raise ValueError("A starting lineup must contain exactly 11 players.")
        if len({p.id for p in self.squad}) != len(self.squad):
            raise ValueError("Players in a match squad must have unique IDs.")
        if sum(p.is_goalkeeper for p in self.lineup) != 1:
            raise ValueError("A starting lineup must contain one goalkeeper.")
