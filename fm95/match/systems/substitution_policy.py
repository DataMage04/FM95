"""Deterministic fatigue management. Thresholds and role weights are provisional."""

from dataclasses import dataclass
from math import isfinite

from fm95.match.systems.fatigue import effective_attributes
from fm95.match.spatial.positions import Position


@dataclass(frozen=True)
class AutoSubstitutionConfig:
    enabled: bool = False
    earliest_second: int = 2700
    condition_threshold: float = .65
    minimum_energy_gain: float = .10
    minimum_suitability: float = .75
    minimum_ability_ratio: float = .8
    minimum_seconds_played: int = 900
    max_changes_per_stoppage: int = 2

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Automatic substitutions enabled must be boolean.")
        for name in ("earliest_second", "minimum_seconds_played", "max_changes_per_stoppage"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer.")
        for name in ("condition_threshold", "minimum_energy_gain", "minimum_suitability", "minimum_ability_ratio"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1].")


@dataclass(frozen=True)
class SubstitutionRecommendation:
    outgoing_id: str
    incoming_id: str
    outgoing_energy: float
    incoming_energy: float
    suitability: float
    ability_gain: float


ROLE_SKILLS = {
    Position.GK: ("shot_stopping", "handling"),
    Position.CB: ("tackling", "heading", "passing"),
    Position.LB: ("tackling", "crossing", "passing"),
    Position.RB: ("tackling", "crossing", "passing"),
    Position.DM: ("tackling", "passing", "heading"),
    Position.CM: ("passing", "dribbling", "tackling"),
    Position.AM: ("passing", "dribbling", "finishing"),
    Position.LW: ("crossing", "dribbling", "finishing"),
    Position.RW: ("crossing", "dribbling", "finishing"),
    Position.ST: ("finishing", "heading", "dribbling"),
}


def suitability(role, natural_position):
    if role == natural_position:
        return 1.0
    if Position.GK in (role, natural_position):
        return 0.0
    if ({role, natural_position} <= {Position.LB, Position.RB}
            or {role, natural_position} <= {Position.LW, Position.RW}
            or {role, natural_position} <= {Position.DM, Position.CM}
            or {role, natural_position} <= {Position.CM, Position.AM}):
        return .8
    return 0.0


def role_ability(attributes, role):
    skills = ROLE_SKILLS[role]
    return sum(getattr(attributes, skill) for skill in skills)/len(skills)


def recommend(active, bench, conditions, elapsed, remaining, config, fatigue, *,
              halftime=False, protected_id=None):
    """Pure recommendation pass; no RNG, mutations, or permanent player ratings.

    Consider the most fatigued players first, then prefer exact positional cover,
    effective role ability, and condition. Player IDs break otherwise equal ties.
    Half-time decisions compare the condition expected after the break.
    """
    if elapsed < config.earliest_second:
        return ()
    recovery = fatigue.halftime_recovery if halftime and fatigue.enabled else 0
    energy = lambda player: min(1, conditions[player.id].energy+recovery)
    candidates = sorted((p for p in active if p.id != protected_id
                         and energy(p) <= config.condition_threshold
                         and conditions[p.id].seconds_played >= config.minimum_seconds_played),
                        key=lambda p: (energy(p), p.id))
    available = list(bench)
    decisions = []
    limit = min(remaining, config.max_changes_per_stoppage)
    for outgoing in candidates:
        if len(decisions) >= limit:
            break
        outgoing_energy = energy(outgoing)
        current_ability = role_ability(effective_attributes(outgoing.attributes, outgoing_energy, fatigue),
                                      outgoing.position)
        options = []
        for incoming in available:
            fit = suitability(outgoing.position, incoming.position)
            incoming_energy = energy(incoming)
            ability = role_ability(effective_attributes(incoming.attributes, incoming_energy, fatigue),
                                   outgoing.position)*fit
            if (fit > 0 and fit >= config.minimum_suitability
                    and incoming_energy-outgoing_energy+1e-9 >= config.minimum_energy_gain
                    and ability >= current_ability*config.minimum_ability_ratio):
                options.append((incoming, fit, ability, incoming_energy))
        if not options:
            continue
        incoming, fit, ability, incoming_energy = min(options,
            key=lambda option: (-option[1], -option[2], -option[3], option[0].id))
        decisions.append(SubstitutionRecommendation(outgoing.id, incoming.id, outgoing_energy,
                                                    incoming_energy, fit, ability-current_ability))
        available.remove(incoming)
    return tuple(decisions)
