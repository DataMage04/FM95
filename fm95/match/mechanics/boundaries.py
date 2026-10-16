"""Point-ball boundary crossings and provisional misplaced-pass exits."""

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from fm95.match.spatial.pitch import Location


class Boundary(str, Enum):
    LEFT = "left_goal_line"
    RIGHT = "right_goal_line"
    BOTTOM = "bottom_touchline"
    TOP = "top_touchline"


@dataclass(frozen=True)
class BoundaryExit:
    boundary: Boundary
    location: Location

    def __post_init__(self):
        if not isinstance(self.boundary, Boundary) or not isinstance(self.location, Location):
            raise ValueError("Exit needs a boundary and location.")
        value = {Boundary.LEFT: self.location.x, Boundary.RIGHT: 1-self.location.x,
                 Boundary.BOTTOM: self.location.y, Boundary.TOP: 1-self.location.y}[self.boundary]
        if abs(value) > 1e-9:
            raise ValueError("Exit location must lie on its boundary.")


@dataclass(frozen=True)
class OutOfPlayConfig:
    enabled: bool = True
    failed_pass_out_probability: float = .25

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Out-of-play enabled must be boolean.")
        value = self.failed_pass_out_probability
        if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Failed-pass out probability must be in [0, 1].")


def first_exit(origin: Location, x: float, y: float) -> BoundaryExit | None:
    """Find first segment crossing. A point on a boundary remains in play.

    Exact corner ties use touchline precedence as an explicit model convention.
    """
    if any(type(value) not in (int, float) or not isfinite(value) for value in (x, y)):
        raise ValueError("Endpoint coordinates must be finite numbers.")
    if 0 <= x <= 1 and 0 <= y <= 1:
        return None
    candidates = []
    for outside, boundary, edge, start, end, priority in (
        (x < 0, Boundary.LEFT, 0, origin.x, x, 1),
        (x > 1, Boundary.RIGHT, 1, origin.x, x, 1),
        (y < 0, Boundary.BOTTOM, 0, origin.y, y, 0),
        (y > 1, Boundary.TOP, 1, origin.y, y, 0),
    ):
        if outside:
            candidates.append(((edge-start)/(end-start), priority, boundary))
    fraction, _, boundary = min(candidates)
    point = Location(max(0, min(1, origin.x+(x-origin.x)*fraction)),
                     max(0, min(1, origin.y+(y-origin.y)*fraction)))
    return BoundaryExit(boundary, point)


def misplaced_endpoint(target: Location, rng) -> tuple[float, float]:
    edges = ("left", "right", "bottom", "top")
    weights = [1/(.05+distance) for distance in (target.x, 1-target.x, target.y, 1-target.y)]
    edge = rng.choices(edges, weights=weights, k=1)[0]
    return {"left": (-.05, target.y), "right": (1.05, target.y),
            "bottom": (target.x, -.05), "top": (target.x, 1.05)}[edge]
