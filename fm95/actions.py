"""Equal-player passing baseline. Probabilities are provisional design values."""

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

    def __post_init__(self):
        if type(self.interval_seconds) is not int or self.interval_seconds < 1:
            raise ValueError("Action interval must be a positive integer.")
        for name in ("completion_probability", "shot_probability",
                     "on_target_probability", "goal_given_on_target_probability"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between 0 and 1.")


def choose_action(zone: Zone, direction: Direction, rng: Random,
                  config: ActionConfig) -> str:
    """Only attacking-third carriers shoot in this coarse baseline."""
    if zone.third_for(direction) == Third.ATTACKING:
        if rng.random() < config.shot_probability:
            return "shot"
    return "pass"


def resolve_shot(rng: Random, config: ActionConfig) -> str:
    """On-target attempts become either goals or held saves; no rebounds yet."""
    if rng.random() >= config.on_target_probability:
        return "shot_missed"
    if rng.random() < config.goal_given_on_target_probability:
        return "goal"
    return "shot_saved"


@dataclass(frozen=True)
class PassResult:
    receiver_id: str
    zone: Zone
    completed: bool
    interceptor_id: str | None


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
    completed = rng.random() < config.completion_probability
    interceptor = None if completed else rng.choice(
        [p for p in defending.lineup if not p.is_goalkeeper]
    ).id
    return PassResult(receiver.id, destination, completed, interceptor)
