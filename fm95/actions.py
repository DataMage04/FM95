"""Contextual actions and provisional player effects; uncalibrated values."""

from dataclasses import dataclass
from random import Random
from typing import TYPE_CHECKING

from fm95.pitch import Direction, Location, Pitch, Third, Zone
from fm95.attributes import ability_multiplier
from fm95.positions import involvement_weight

if TYPE_CHECKING:
    from fm95.match import Possession, Team, TeamInPlay


@dataclass(frozen=True)
class ActionConfig:
    interval_seconds: int = 6
    completion_probability: float = 0.85
    shot_probability: float = 0.12
    on_target_probability: float = 0.40
    goal_given_on_target_probability: float = 0.25
    context_strength: float = 1.0
    attribute_strength: float = 1.0
    dribble_probability: float = 0.15
    dribble_success_probability: float = 0.60
    foul_probability: float = 0.08
    straight_red_probability: float = 0.01
    yellow_card_probability: float = 0.20

    def __post_init__(self):
        if type(self.interval_seconds) is not int or self.interval_seconds < 1:
            raise ValueError("Action interval must be a positive integer.")
        for name in ("completion_probability", "shot_probability",
                     "on_target_probability", "goal_given_on_target_probability", "context_strength",
                     "attribute_strength", "dribble_probability", "dribble_success_probability",
                     "foul_probability", "straight_red_probability", "yellow_card_probability"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between 0 and 1.")


def foul_card(rng: Random, config: ActionConfig) -> str | None:
    """Provisional sanctions: red first, then conditional yellow; no severity model yet."""
    if config.straight_red_probability > 0 and rng.random() < config.straight_red_probability:
        return "red"
    if config.yellow_card_probability > 0 and rng.random() < config.yellow_card_probability:
        return "yellow"
    return None


def adjust_probability(base: float, multiplier: float, strength: float) -> float:
    """Scale odds smoothly while preserving forced 0/1 outcomes for testing.

    multiplier is interpolated from neutral (1) by strength, then applied to odds.
    """
    factor = 1 + strength * (multiplier - 1)
    return base * factor / (1 - base + base * factor)


def pass_completion_chance(origin: Zone, destination: Zone, direction: Direction,
                           config: ActionConfig, *, passing: float = 0.5,
                           pressure: float = 0, pressure_effect: float = .4) -> float:
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
    contextual = adjust_probability(config.completion_probability, multiplier, config.context_strength)
    ability = adjust_probability(contextual, ability_multiplier(passing - 0.5, config.attribute_strength), 1)
    return adjust_probability(ability, max(.01, 1-pressure_effect*pressure), 1)


def shot_probabilities(zone: Zone, config: ActionConfig, *, finishing: float = 0.5,
                       shot_stopping: float = 0.5, pressure: float = 0,
                       pressure_effect: float = .4) -> tuple[float, float]:
    """Return on-target and conditional scoring probabilities before any draws."""
    central = zone.lane == 1
    on_target = adjust_probability(config.on_target_probability,
                                   1.20 if central else 0.80, config.context_strength)
    goal_given_target = adjust_probability(config.goal_given_on_target_probability,
                                           1.25 if central else 0.70, config.context_strength)
    on_target = adjust_probability(on_target,
        ability_multiplier(finishing - 0.5, config.attribute_strength), 1)
    goal_given_target = adjust_probability(goal_given_target,
        ability_multiplier(finishing - shot_stopping, config.attribute_strength), 1)
    on_target = adjust_probability(on_target, max(.01, 1-pressure_effect*pressure), 1)
    return on_target, goal_given_target


def choose_action(zone: Zone, direction: Direction, rng: Random,
                  config: ActionConfig, *, can_dribble: bool = True) -> str:
    """Only attacking-third carriers shoot in this coarse baseline."""
    if zone.third_for(direction) == Third.ATTACKING:
        probability = adjust_probability(config.shot_probability,
                                         1.25 if zone.lane == 1 else 0.75,
                                         config.context_strength)
        if rng.random() < probability:
            return "shot"
    # Conditional choice after declining a shot, not an additive probability.
    if can_dribble and config.dribble_probability > 0 and rng.random() < config.dribble_probability:
        return "dribble"
    return "pass"


def dribble_success_chance(dribbling: float, tackling: float, config: ActionConfig) -> float:
    return adjust_probability(config.dribble_success_probability,
        ability_multiplier(dribbling - tackling, config.attribute_strength), 1)


def press_win_chance(tackling: float, dribbling: float, base: float, strength: float) -> float:
    return adjust_probability(base, ability_multiplier(tackling-dribbling, strength), 1)


def spatial_involvement(player, destination: Zone, direction: Direction, locations, pitch) -> float:
    if locations is None or pitch is None:
        return involvement_weight(player.position, destination, direction)
    distance = pitch.distance(locations[player.id], Location.centre_of(destination))
    return 1 / (1+distance/10) ** 2


@dataclass(frozen=True)
class DribbleResult:
    defender_id: str
    destination: Zone
    completed: bool
    success_probability: float
    defender_tackling: float
    fouled: bool = False


def resolve_dribble(possession: "Possession", attacking: "Team | TeamInPlay", defending: "Team | TeamInPlay",
                    direction: Direction, rng: Random, config: ActionConfig, *,
                    locations=None, pitch: Pitch | None = None) -> DribbleResult:
    """A direct contest: win advances the carrier; loss leaves ball at the challenge zone."""
    carrier = next(p for p in attacking.lineup if p.id == possession.player_id)
    defenders = [p for p in defending.lineup if not p.is_goalkeeper]
    defender = rng.choices(defenders, weights=[
        (1 / (1+pitch.distance(locations[p.id], possession.location)/10) ** 2
         if locations is not None and pitch is not None else
         involvement_weight(p.position, possession.zone, Direction(-int(direction))))
        for p in defenders
    ], k=1)[0]
    origin = possession.zone
    column = origin.column + int(direction)
    if 0 <= column <= 2:
        destination = Zone(column, origin.lane)
    else:
        # At the attacking edge a successful take-on shifts laterally, never off pitch.
        destination = rng.choice([Zone(origin.column, lane)
                                  for lane in (origin.lane - 1, origin.lane + 1) if 0 <= lane <= 2])
    probability = dribble_success_chance(carrier.attributes.dribbling,
                                         defender.attributes.tackling, config)
    if config.foul_probability > 0 and rng.random() < config.foul_probability:
        return DribbleResult(defender.id, origin, False, probability,
                             defender.attributes.tackling, fouled=True)
    return DribbleResult(defender.id, destination, rng.random() < probability,
                         probability, defender.attributes.tackling)


@dataclass(frozen=True)
class ShotResult:
    outcome: str
    on_target_probability: float
    goal_probability: float
    block_probability: float = 0


def resolve_shot(zone: Zone, rng: Random, config: ActionConfig, *, finishing: float = 0.5,
                 shot_stopping: float = 0.5, pressure: float = 0,
                 pressure_effect: float = .4, block_probability: float = 0,
                 parry_probability: float = 0) -> ShotResult:
    """Resolve obstruction, accuracy, conversion, then held/parried saves."""
    on_target, goal_given_target = shot_probabilities(zone, config, finishing=finishing,
                                                     shot_stopping=shot_stopping, pressure=pressure,
                                                     pressure_effect=pressure_effect)
    goal_probability = (1-block_probability)*on_target*goal_given_target
    target_probability = (1-block_probability)*on_target
    if block_probability > 0 and rng.random() < block_probability:
        return ShotResult("shot_blocked", target_probability, goal_probability, block_probability)
    if rng.random() >= on_target:
        outcome = "shot_missed"
    elif rng.random() < goal_given_target:
        outcome = "goal"
    else:
        outcome = ("shot_parried" if parry_probability > 0 and rng.random() < parry_probability
                   else "shot_saved")
    return ShotResult(outcome, target_probability, goal_probability, block_probability)


@dataclass(frozen=True)
class PassResult:
    receiver_id: str
    zone: Zone
    completed: bool
    interceptor_id: str | None
    completion_probability: float


def resolve_pass(possession: "Possession", attacking: "Team | TeamInPlay", defending: "Team | TeamInPlay",
                 direction: Direction, rng: Random, config: ActionConfig, *,
                 pressure: float = 0, pressure_effect: float = .4,
                 locations=None, pitch: Pitch | None = None) -> PassResult:
    """Choose an outfield receiver and nearby destination, then resolve the pass.

    Forward destinations have weight 3; sideways and backward destinations weight 1.
    All legal choices remain inside the pitch. Assigned operating zones weight
    receivers and interceptors; these are not actual player coordinates.
    """
    receivers = [p for p in attacking.lineup
                 if not p.is_goalkeeper and p.id != possession.player_id]
    origin = possession.zone
    destinations = [origin]
    weights = [1]
    for dx, dy in ((int(direction), 0), (-int(direction), 0), (0, -1), (0, 1)):
        column, lane = origin.column + dx, origin.lane + dy
        if 0 <= column <= 2 and 0 <= lane <= 2:
            destinations.append(Zone(column, lane))
            weights.append(3 if dx == int(direction) else 1)
    destination = rng.choices(destinations, weights=weights, k=1)[0]
    receiver = rng.choices(receivers, weights=[
        spatial_involvement(p, destination, direction, locations, pitch) for p in receivers
    ], k=1)[0]
    passer = next(p for p in attacking.lineup if p.id == possession.player_id)
    probability = pass_completion_chance(origin, destination, direction, config,
                                         passing=passer.attributes.passing, pressure=pressure,
                                         pressure_effect=pressure_effect)
    completed = rng.random() < probability
    interceptor = None
    if not completed:
        defenders = [p for p in defending.lineup if not p.is_goalkeeper]
        defending_direction = Direction(-int(direction))
        interceptor = rng.choices(defenders, weights=[
            spatial_involvement(p, destination, defending_direction, locations, pitch) for p in defenders
        ], k=1)[0].id
    return PassResult(receiver.id, destination, completed, interceptor, probability)
