"""Assigned positions and coarse operating zones, not tracked player coordinates."""

from enum import Enum

from fm95.pitch import Direction, Location, Zone


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


REFERENCE_POINTS = {
    Position.GK: Location(.05, .5), Position.CB: Location(.22, .5),
    Position.LB: Location(.25, .84), Position.RB: Location(.25, .16),
    Position.DM: Location(.38, .5), Position.CM: Location(.50, .5), Position.AM: Location(.62, .5),
    Position.LW: Location(.82, .84), Position.RW: Location(.82, .16), Position.ST: Location(.82, .5),
}


def formation_reference_locations(players, direction: Direction) -> dict[str, Location]:
    """Return static shape targets; repeated central positions share the line across lanes."""
    locations = {}
    for position in Position:
        group = [p for p in players if p.position == position]
        for index, player in enumerate(group):
            point = REFERENCE_POINTS[position]
            if len(group) > 1:
                y = max(.01, min(.99, point.y + .30 * (index/(len(group)-1) - .5)))
                point = Location(point.x, y)
            locations[player.id] = point if direction == Direction.RIGHT else point.rotated()
    return locations
