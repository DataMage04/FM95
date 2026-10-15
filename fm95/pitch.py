"""A fixed pitch grid: x increases left to right, y from bottom to top.

Zones describe ball location, not individual player positions.
"""

from dataclasses import dataclass
from enum import Enum, IntEnum


class Direction(IntEnum):
    LEFT = -1
    RIGHT = 1


class Third(str, Enum):
    DEFENSIVE = "defensive"
    MIDDLE = "middle"
    ATTACKING = "attacking"


@dataclass(frozen=True)
class Zone:
    column: int
    lane: int

    def __post_init__(self):
        if any(type(value) is not int or value not in range(3)
               for value in (self.column, self.lane)):
            raise ValueError("Zone column and lane must be integers from 0 to 2.")

    def third_for(self, direction: Direction) -> Third:
        direction = Direction(direction)
        progress = self.column if direction == Direction.RIGHT else 2 - self.column
        return (Third.DEFENSIVE, Third.MIDDLE, Third.ATTACKING)[progress]


CENTRE = Zone(1, 1)
