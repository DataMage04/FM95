"""Represented stoppage delays and per-half allowance (IFAB Law 7).

Durations are provisional simulation policies, not prescribed football values.
Only actually consumed delay seconds are compensated. Ordinary restart cadence
is not counted wholesale as lost time.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AddedTimeConfig:
    enabled: bool = False
    substitution_seconds: int = 20
    injury_seconds: int = 30
    goal_seconds: int = 20
    discipline_seconds: int = 5
    rounding_seconds: int = 60

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Added time enabled must be boolean.")
        for name in ('substitution_seconds','injury_seconds','goal_seconds','discipline_seconds'):
            value = getattr(self,name)
            if type(value) is not int or value<0:
                raise ValueError(f"{name} must be a nonnegative integer.")
        if type(self.rounding_seconds) is not int or self.rounding_seconds<1:
            raise ValueError("Added-time rounding must be a positive integer.")


@dataclass(frozen=True)
class PeriodTiming:
    period: int
    period_elapsed_seconds: int
    time_lost_seconds: int
    minimum_added_seconds: int | None
    target_end_seconds: int
    restart_delay_seconds: int
