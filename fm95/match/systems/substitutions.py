"""Configurable competition limits and immutable substitution usage snapshots."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SubstitutionConfig:
    max_substitutions: int = 5
    max_windows: int = 3

    def __post_init__(self):
        for name in ("max_substitutions", "max_windows"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer.")


@dataclass(frozen=True)
class SubstitutionStatus:
    used: int
    remaining: int
    windows_used: int
    windows_remaining: int
