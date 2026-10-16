"""A fixed pitch grid: x increases left to right, y from bottom to top.

Zones describe ball location, not individual player positions.
"""

from dataclasses import dataclass
from enum import Enum, IntEnum
from math import hypot, isfinite


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


@dataclass(frozen=True)
class Location:
    """Normalized fixed-pitch coordinates: x left→right, y bottom→top."""
    x: float
    y: float

    def __post_init__(self):
        for value in (self.x, self.y):
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Location coordinates must be finite numbers in [0, 1].")

    @property
    def zone(self) -> Zone:
        return Zone(min(2, int(self.x * 3)), min(2, int(self.y * 3)))

    @classmethod
    def centre_of(cls, zone: Zone) -> "Location":
        return cls((zone.column + .5) / 3, (zone.lane + .5) / 3)

    def rotated(self) -> "Location":
        return Location(1 - self.x, 1 - self.y)

    def shifted_to(self, zone: Zone) -> "Location":
        """Translate between grid cells, retaining within-cell offset away from edges."""
        old = self.zone
        x_offset = min(1-1e-9, max(1e-9, self.x*3-old.column))
        y_offset = min(1-1e-9, max(1e-9, self.y*3-old.lane))
        return Location((zone.column+x_offset)/3, (zone.lane+y_offset)/3)


@dataclass(frozen=True)
class Pitch:
    """Metric geometry independent of simulation probability settings."""
    length: float = 105.0
    width: float = 68.0
    penalty_depth: float = 16.5
    goal_width: float = 7.32

    def __post_init__(self):
        for value in (self.length, self.width, self.penalty_depth, self.goal_width):
            if type(value) not in (int, float) or not isfinite(value) or value <= 0:
                raise ValueError("Pitch dimensions must be finite positive numbers.")
        if 2 * self.penalty_depth >= self.length or self.penalty_width > self.width:
            raise ValueError("Penalty areas must fit inside the pitch without overlapping.")

    @property
    def penalty_width(self) -> float:
        return self.goal_width + 2 * self.penalty_depth

    def metres(self, location: Location) -> tuple[float, float]:
        return location.x * self.length, location.y * self.width

    def from_metres(self, x: float, y: float) -> Location:
        return Location(x / self.length, y / self.width)

    def distance(self, first: Location, second: Location) -> float:
        return hypot((first.x-second.x) * self.length, (first.y-second.y) * self.width)

    def in_penalty_area(self, location: Location, defending_direction: Direction) -> bool:
        """Area defended by a team attacking in defending_direction; includes boundary."""
        direction = Direction(defending_direction)
        depth = location.x * self.length if direction == Direction.RIGHT else (1-location.x) * self.length
        lateral = abs(location.y-.5) * self.width
        return depth <= self.penalty_depth + 1e-9 and lateral <= self.penalty_width/2 + 1e-9
