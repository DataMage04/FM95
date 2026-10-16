"""Stable player identity and match-relevant player data."""

from dataclasses import dataclass, field

from fm95.match.spatial.positions import Position
from fm95.players.attributes import Attributes
from fm95.players.decisions import DecisionTendencies


@dataclass(frozen=True)
class Player:
    id: str
    name: str
    is_goalkeeper: bool = False
    attributes: Attributes = field(default_factory=Attributes)
    position: Position | None = None
    decisions: DecisionTendencies = field(default_factory=DecisionTendencies)

    def __post_init__(self):
        if not isinstance(self.attributes, Attributes):
            raise ValueError("Player attributes must be an Attributes instance.")
        if not isinstance(self.decisions, DecisionTendencies):
            raise ValueError("Player decisions must be a DecisionTendencies instance.")
        if self.position is None:
            object.__setattr__(self, "position", Position.GK if self.is_goalkeeper else Position.CM)
        if not isinstance(self.position, Position):
            raise ValueError("Player position must be a Position enum value.")
        if (self.position == Position.GK) != self.is_goalkeeper:
            raise ValueError("Goalkeeper designation and position must agree.")
