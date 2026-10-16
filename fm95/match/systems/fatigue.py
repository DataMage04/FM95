"""Provisional condition model, independent of a player's permanent attributes."""

from dataclasses import dataclass, fields, replace
from math import isfinite

from fm95.players.attributes import Attributes


@dataclass(frozen=True)
class FatigueConfig:
    enabled: bool = True
    drain_per_second: float = .0001
    drain_per_metre: float = .00001
    stoppage_recovery_per_second: float = .00003
    halftime_recovery: float = .10
    stamina_effect: float = .5
    goalkeeper_load: float = .4
    effect_threshold: float = .8
    max_attribute_penalty: float = .3
    max_movement_penalty: float = .4

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Fatigue enabled must be boolean.")
        for item in fields(self):
            if item.name == "enabled":
                continue
            value = getattr(self, item.name)
            if type(value) not in (int, float) or not isfinite(value) or value < 0:
                raise ValueError(f"{item.name} must be finite and nonnegative.")
            if item.name not in ("drain_per_second", "drain_per_metre", "stoppage_recovery_per_second") and value > 1:
                raise ValueError(f"{item.name} must be in [0, 1].")
        if self.effect_threshold == 0:
            raise ValueError("Fatigue effect threshold must be positive.")


@dataclass(frozen=True)
class PlayerCondition:
    energy: float = 1.0
    seconds_played: int = 0
    distance_covered: float = 0.0

    def __post_init__(self):
        if type(self.energy) not in (int, float) or not isfinite(self.energy) or not 0 <= self.energy <= 1:
            raise ValueError("Energy must be finite and in [0, 1].")
        if type(self.seconds_played) is not int or self.seconds_played < 0:
            raise ValueError("Playing time must be a nonnegative integer.")
        if (type(self.distance_covered) not in (int, float) or not isfinite(self.distance_covered)
                or self.distance_covered < 0):
            raise ValueError("Distance must be finite and nonnegative.")


def workload_factor(stamina, config):
    return 1+config.stamina_effect*(.5-stamina)


def tick(condition, stamina, goalkeeper, resting, config, *, load=1):
    energy = condition.energy
    if config.enabled:
        delta = (config.stoppage_recovery_per_second if resting else
                 -config.drain_per_second*load*workload_factor(stamina, config)
                 * (config.goalkeeper_load if goalkeeper else 1))
        energy = max(0, min(1, energy+delta))
    return replace(condition, energy=energy, seconds_played=condition.seconds_played+1)


def movement(condition, metres, stamina, config):
    cost = metres*config.drain_per_metre*workload_factor(stamina, config) if config.enabled else 0
    return replace(condition, energy=max(0, condition.energy-cost),
                   distance_covered=condition.distance_covered+metres)


def severity(energy, config):
    return max(0, (config.effect_threshold-energy)/config.effect_threshold) if config.enabled else 0


def movement_factor(energy, config):
    return 1-config.max_movement_penalty*severity(energy, config)


def effective_attributes(attributes: Attributes, energy, config):
    factor = 1-config.max_attribute_penalty*severity(energy, config)
    if factor == 1:
        return attributes
    return replace(attributes, **{item.name: getattr(attributes, item.name)*factor
                                  for item in fields(attributes) if item.name not in ("stamina", "injury_proneness")})
