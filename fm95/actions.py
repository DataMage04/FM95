"""Equal-player actions with coarse situational context; uncalibrated values."""

from dataclasses import dataclass
from random import Random
from typing import TYPE_CHECKING

from fm95.pitch import Direction, Third, Zone

if TYPE_CHECKING:
    from fm95.match import Possession, Team


@dataclass(frozen=True)
class ActionConfig:
    interval_seconds: int = 6
    completion_probability: float = 0.85
    shot_probability: float = 0.12
    on_target_probability: float = 0.40
    goal_given_on_target_probability: float = 0.25
    context_strength: float = 1.0

    def __post_init__(self):
        if type(self.interval_seconds) is not int or self.interval_seconds < 1:
            raise ValueError("Action interval must be a positive integer.")
        for name in ("completion_probability", "shot_probability",
                     "on_target_probability", "goal_given_on_target_probability", "context_strength"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between 0 and 1.")


def adjust_probability(base: float, multiplier: float, strength: float) -> float:
    """Scale odds smoothly while preserving forced 0/1 outcomes for testing.

    multiplier is interpolated from neutral (1) by strength, then applied to odds.
    """
    factor = 1 + strength * (multiplier - 1)
    return base * factor / (1 - base + base * factor)


def pass_completion_chance(origin: Zone, destination: Zone, direction: Direction,
                           config: ActionConfig) -> float:
    progress = (destination.column - origin.column) * int(direction)
    if progress > 0:
        multiplier = 0.75
    elif progress < 0:
        multiplier = 1.20
    elif destination == origin:
        multiplier = 1.25
    else:
        multiplier = 1.0
    # A coarse pressure proxy, not a calculation from defender positions.
    if origin.third_for(direction) == Third.ATTACKING:
        multiplier *= 0.85
    return adjust_probability(config.completion_probability, multiplier, config.context_strength)


def shot_probabilities(zone: Zone, config: ActionConfig) -> tuple[float, float]:
    """Return on-target and conditional scoring probabilities before any draws."""
    central = zone.lane == 1
    on_target = adjust_probability(config.on_target_probability,
                                   1.20 if central else 0.80, config.context_strength)
    goal_given_target = adjust_probability(config.goal_given_on_target_probability,
                                           1.25 if central else 0.70, config.context_strength)
    return on_target, goal_given_target


def choose_action(zone: Zone, direction: Direction, rng: Random,
                  config: ActionConfig) -> str:
    """Only attacking-third carriers shoot in this coarse baseline."""
    if zone.third_for(direction) == Third.ATTACKING:
        probability = adjust_probability(config.shot_probability,
                                         1.25 if zone.lane == 1 else 0.75,
                                         config.context_strength)
        if rng.random() < probability:
            return "shot"
    return "pass"


@dataclass(frozen=True)
class ShotResult:
    outcome: str
    on_target_probability: float
    goal_probability: float


def resolve_shot(zone: Zone, rng: Random, config: ActionConfig) -> ShotResult:
    """On-target attempts become either goals or held saves; no rebounds yet."""
    on_target, goal_given_target = shot_probabilities(zone, config)
    if rng.random() >= on_target:
        outcome = "shot_missed"
    elif rng.random() < goal_given_target:
        outcome = "goal"
    else:
        outcome = "shot_saved"
    return ShotResult(outcome, on_target, on_target * goal_given_target)


@dataclass(frozen=True)
class PassResult:
    receiver_id: str
    zone: Zone
    completed: bool
    interceptor_id: str | None
    completion_probability: float


def resolve_pass(possession: "Possession", attacking: "Team", defending: "Team",
                 direction: Direction, rng: Random, config: ActionConfig) -> PassResult:
    """Choose an outfield receiver and nearby destination, then resolve the pass.

    Forward destinations have weight 3; sideways and backward destinations weight 1.
    All legal choices remain inside the pitch. Receivers have no spatial positions
    yet, so all other outfield teammates are equally eligible.
    """
    receivers = [p for p in attacking.lineup
                 if not p.is_goalkeeper and p.id != possession.player_id]
    receiver = rng.choice(receivers)
    origin = possession.zone
    destinations = [origin]
    weights = [1]
    for dx, dy in ((int(direction), 0), (-int(direction), 0), (0, -1), (0, 1)):
        column, lane = origin.column + dx, origin.lane + dy
        if 0 <= column <= 2 and 0 <= lane <= 2:
            destinations.append(Zone(column, lane))
            weights.append(3 if dx == int(direction) else 1)
    destination = rng.choices(destinations, weights=weights, k=1)[0]
    probability = pass_completion_chance(origin, destination, direction, config)
    completed = rng.random() < probability
    interceptor = None if completed else rng.choice(
        [p for p in defending.lineup if not p.is_goalkeeper]
    ).id
    return PassResult(receiver.id, destination, completed, interceptor, probability)
