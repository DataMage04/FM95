"""Individual duties influence intent, never a player's underlying ability.

All effects are provisional until the end-of-milestone calibration pass.
"""
from dataclasses import replace
from enum import Enum

from fm95.match.spatial.pitch import Location


class Duty(str, Enum):
    BALANCED = "balanced"
    DEFEND = "defend"
    SUPPORT = "support"
    ATTACK = "attack"


def instructions_for(tactics, duty):
    """Combine a player's duty with team preferences; neutral preserves defaults."""
    offsets = {
        Duty.BALANCED: {},
        Duty.DEFEND: {"shooting": -.2, "dribbling": -.2, "passing_directness": -.15},
        Duty.SUPPORT: {"shooting": -.15, "through_balls": .2},
        Duty.ATTACK: {"shooting": .2, "dribbling": .15, "passing_directness": .15},
    }[duty]
    return replace(tactics, **{key: max(0, min(1, getattr(tactics, key)+value))
                              for key, value in offsets.items()}) if offsets else tactics


def duty_target(point, direction, duty):
    shift = {Duty.BALANCED: 0, Duty.DEFEND: -.07,
             Duty.SUPPORT: -.025, Duty.ATTACK: .07}[duty]
    return Location(max(.01, min(.99, point.x+int(direction)*shift)), point.y) if shift else point
