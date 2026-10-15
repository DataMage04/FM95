"""Uncontrolled-ball state and provisional recovery settings."""

from dataclasses import dataclass
from math import isfinite

from fm95.pitch import Location


@dataclass(frozen=True)
class LooseBall:
    location: Location
    last_team_id: str | None
    last_player_id: str | None
    reason: str


@dataclass(frozen=True)
class RecoveryConfig:
    enabled: bool = True
    misplaced_pass_probability: float = .35
    tackle_loose_probability: float = .25
    movement_speed: float = 4.0
    control_radius: float = 1.5

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Recovery enabled must be boolean.")
        for name in ("misplaced_pass_probability", "tackle_loose_probability"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1].")
        for name in ("movement_speed", "control_radius"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative.")
