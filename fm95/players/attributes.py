"""Temporary normalized development attributes; final ranges are deferred."""

from dataclasses import dataclass
from math import exp, isfinite


@dataclass(frozen=True)
class Attributes:
    passing: float = 0.5
    finishing: float = 0.5
    shot_stopping: float = 0.5
    dribbling: float = 0.5
    tackling: float = 0.5
    crossing: float = 0.5
    heading: float = 0.5
    handling: float = 0.5
    penalties: float = 0.5
    free_kicks: float = 0.5
    stamina: float = 0.5
    injury_proneness: float = 0.5

    def __post_init__(self):
        for name in ("passing", "finishing", "shot_stopping", "dribbling", "tackling", "crossing", "heading", "handling",
                     "penalties", "free_kicks", "stamina", "injury_proneness"):
            value = getattr(self, name)
            if (type(value) not in (int, float) or not isfinite(value)
                    or not 0 <= value <= 1):
                raise ValueError(f"{name} must be a finite number between 0 and 1.")


def ability_multiplier(advantage: float, strength: float) -> float:
    """Provisional odds response: neutral advantage gives multiplier 1.

    Keep the response in one place for end-of-milestone calibration.
    """
    return exp(2 * strength * advantage)
