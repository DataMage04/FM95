"""Forward runs into space; constants remain provisional until milestone calibration."""

from dataclasses import dataclass
from math import isfinite

from fm95.match.mechanics.actions import adjust_probability
from fm95.players.attributes import ability_multiplier
from fm95.match.spatial.pitch import Location


@dataclass(frozen=True)
class ThroughBallConfig:
    enabled: bool = True
    choice_probability: float = .20
    completion_probability: float = .60
    run_distance: float = 8.0

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Through balls enabled must be boolean.")
        for name in ("choice_probability", "completion_probability"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1].")
        if (type(self.run_distance) not in (int, float)
                or not isfinite(self.run_distance) or self.run_distance <= 0):
            raise ValueError("Run distance must be finite and positive.")


def forward_runs(players, locations, carrier_id, origin, direction, pitch, config, *, movement_factors=None):
    """Eligible receivers and reachable targets, excluding runs over the goal line."""
    runs = []
    for player in players:
        start = locations[player.id]
        factor = movement_factors.get(player.id, 1) if movement_factors is not None else 1
        if factor <= 0:
            continue
        target_x = start.x + direction * config.run_distance * factor / pitch.length
        if (not player.is_goalkeeper and player.id != carrier_id
                and (start.x-origin.x)*direction > 0 and 0 < target_x < 1):
            runs.append((player.id, start, Location(target_x, start.y)))
    return runs


def completion_chance(passing, pressure, strength, pressure_effect, config):
    chance = adjust_probability(config.completion_probability,
                                 ability_multiplier(passing-.5, strength), 1)
    return adjust_probability(chance, max(.01, 1-pressure*pressure_effect), 1)
