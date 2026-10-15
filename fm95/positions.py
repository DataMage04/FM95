"""Assigned positions and coarse operating zones, not tracked player coordinates."""

from enum import Enum

from fm95.pitch import Direction, Zone


class Position(str, Enum):
    GK = "GK"
    CB = "CB"
    LB = "LB"
    RB = "RB"
    DM = "DM"
    CM = "CM"
    AM = "AM"
    LW = "LW"
    RW = "RW"
    ST = "ST"


ANCHORS = {
    Position.GK: Zone(0, 1), Position.CB: Zone(0, 1),
    Position.LB: Zone(0, 2), Position.RB: Zone(0, 0),
    Position.DM: Zone(1, 1), Position.CM: Zone(1, 1), Position.AM: Zone(1, 1),
    Position.LW: Zone(2, 2), Position.RW: Zone(2, 0), Position.ST: Zone(2, 1),
}


def operating_zone(position: Position, direction: Direction) -> Zone:
    anchor = ANCHORS[position]
    return anchor if direction == Direction.RIGHT else Zone(2 - anchor.column, 2 - anchor.lane)


def involvement_weight(position: Position, destination: Zone, direction: Direction) -> float:
    anchor = operating_zone(position, direction)
    distance = abs(anchor.column - destination.column) + abs(anchor.lane - destination.lane)
    return 1 / (1 + distance) ** 2
