"""Spatial shot obstruction and in-play rebound geometry; provisional behavior."""

from dataclasses import dataclass
from math import cos, sin, pi, isfinite

from fm95.pitch import Direction, Location, Pitch


@dataclass(frozen=True)
class ShotConfig:
    enabled: bool = True
    block_probability: float = .35
    block_radius: float = 3.0
    parry_probability: float = .30
    rebound_distance: float = 8.0

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Shot interactions enabled must be boolean.")
        for name in ("block_probability", "parry_probability"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1].")
        for name in ("block_radius", "rebound_distance"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative.")


def blocking_context(defenders, locations, origin: Location, direction: Direction,
                     pitch: Pitch, config: ShotConfig) -> tuple[str | None, float]:
    """Only active outfield defenders between the shooter and goal may block."""
    if not config.enabled or config.block_radius <= 0:
        return None, 0
    ox, oy = pitch.metres(origin)
    goal_x = pitch.length if direction == Direction.RIGHT else 0
    vx, vy = goal_x-ox, pitch.width/2-oy
    length_squared = vx*vx+vy*vy
    if not length_squared:
        return None, 0
    candidates = []
    for player in defenders:
        if player.is_goalkeeper:
            continue
        px, py = pitch.metres(locations[player.id])
        fraction = ((px-ox)*vx+(py-oy)*vy)/length_squared
        if 0 < fraction < 1:
            distance = ((px-ox-fraction*vx)**2+(py-oy-fraction*vy)**2)**.5
            if distance < config.block_radius:
                candidates.append((distance, player.id))
    if not candidates:
        return None, 0
    distance, player_id = min(candidates)
    return player_id, config.block_probability*(1-distance/config.block_radius)


def rebound_endpoint(origin: Location, pitch: Pitch, rng, distance: float) -> tuple[float, float]:
    if distance == 0:
        return origin.x, origin.y
    angle = rng.random()*2*pi
    radius = distance*(.25+.75*rng.random())
    return origin.x+radius*cos(angle)/pitch.length, origin.y+radius*sin(angle)/pitch.width


def rebound_location(origin: Location, pitch: Pitch, rng, distance: float) -> Location:
    """Legacy in-play endpoint when boundary interactions are disabled."""
    if distance == 0:
        return origin
    x, y = rebound_endpoint(origin, pitch, rng, distance)
    return Location(max(1e-6, min(1-1e-6, x)), max(1e-6, min(1-1e-6, y)))
