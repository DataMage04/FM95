"""Penalty and direct free-kick foundations; probabilities await calibration."""

from dataclasses import dataclass, replace
from math import isfinite

from fm95.match.mechanics.actions import adjust_probability, resolve_shot
from fm95.match.spatial.pitch import Direction, Location


@dataclass(frozen=True)
class SetPieceConfig:
    enabled: bool = True
    direct_shot_probability: float = .5
    direct_shot_range: float = 32.0
    penalty_on_target_probability: float = .9
    penalty_goal_given_on_target_probability: float = .8
    free_kick_on_target_probability: float = .4
    free_kick_goal_given_on_target_probability: float = .25

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Set pieces enabled must be boolean.")
        for name in ("direct_shot_probability", "penalty_on_target_probability",
                     "penalty_goal_given_on_target_probability", "free_kick_on_target_probability",
                     "free_kick_goal_given_on_target_probability"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1].")
        if (type(self.direct_shot_range) not in (int, float)
                or not isfinite(self.direct_shot_range) or self.direct_shot_range <= 0):
            raise ValueError("Direct shot range must be finite and positive.")


def goal_centre(direction):
    return Location(1 if direction == Direction.RIGHT else 0, .5)


def penalty_mark(pitch, direction):
    # 11 m on the standard pitch; scales with deliberately resized penalty areas.
    distance = pitch.penalty_depth * 2/3
    x = pitch.length-distance if direction == Direction.RIGHT else distance
    return pitch.from_metres(x, pitch.width/2)


def can_shoot_free_kick(location, direction, pitch, config):
    return ((location.x-.5)*direction > 0
            and pitch.distance(location, goal_centre(direction)) <= config.direct_shot_range)


def resolve_set_piece(location, direction, pitch, rng, actions, config, *, penalty,
                      ability, shot_stopping, block_probability=0, parry_probability=0):
    if penalty:
        accuracy, conversion = (config.penalty_on_target_probability,
                                config.penalty_goal_given_on_target_probability)
    else:
        accuracy, conversion = (config.free_kick_on_target_probability,
                                config.free_kick_goal_given_on_target_probability)
        distance = pitch.distance(location, goal_centre(direction))
        # Continuous metric context instead of the coarse open-play zone proxy.
        angle = abs(goal_centre(direction).x-location.x)*pitch.length/max(distance, 1e-9)
        factor = max(.01, angle*25/max(distance, 1))
        accuracy = adjust_probability(accuracy, factor, actions.context_strength)
        conversion = adjust_probability(conversion, factor, actions.context_strength)
    config_for_shot = replace(actions, context_strength=0, on_target_probability=accuracy,
                              goal_given_on_target_probability=conversion)
    return resolve_shot(location.zone, rng, config_for_shot, finishing=ability,
                        shot_stopping=shot_stopping, block_probability=0 if penalty else block_probability,
                        parry_probability=parry_probability)
