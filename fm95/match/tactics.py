"""Per-team instructions: 0 is low, .5 balanced, 1 high. Effects are provisional."""

from dataclasses import dataclass, fields, replace
from math import isfinite

from fm95.match.mechanics.actions import ActionConfig, adjust_probability, instruction_multiplier
from fm95.match.spatial.pitch import Location
from fm95.match.spatial.positions import Position


@dataclass(frozen=True)
class TeamTactics:
    tempo: float = .5
    pressing: float = .5
    defensive_line: float = .5
    width: float = .5
    passing_directness: float = .5
    crossing: float = .5
    dribbling: float = .5
    shooting: float = .5
    through_balls: float = .5

    def __post_init__(self):
        for item in fields(self):
            value = getattr(self, item.name)
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{item.name} must be finite and in [0, 1].")


def preference(base, instruction):
    return adjust_probability(base, instruction_multiplier(instruction), 1)


def action_interval(base_seconds, tactics):
    return max(1, round(base_seconds/instruction_multiplier(tactics.tempo)))


def action_preferences(base: ActionConfig, tactics):
    if tactics.shooting == tactics.dribbling == .5:
        return base
    return replace(base, shot_probability=preference(base.shot_probability, tactics.shooting),
                   dribble_probability=preference(base.dribble_probability, tactics.dribbling))


def workload(tactics, has_ball):
    return 1+.5*((tactics.tempo if has_ball else tactics.pressing)-.5)


def shape_targets(players, references, direction, tactics):
    result = dict(references)
    for player in players:
        if player.is_goalkeeper:
            continue
        point = references[player.id]
        line_shift = ((tactics.defensive_line-.5)*.2
                      if player.position in (Position.CB, Position.LB, Position.RB) else
                      (tactics.defensive_line-.5)*.1 if player.position == Position.DM else 0)
        x = max(.01, min(.99, point.x+int(direction)*line_shift)) if line_shift else point.x
        y = (max(.01, min(.99, .5+(point.y-.5)*(.75+.5*tactics.width)))
             if tactics.width != .5 else point.y)
        result[player.id] = Location(x, y)
    return result


def preset(name):
    """Example instructions for demos, not calibrated tactical recommendations."""
    profiles = {
        "balanced": TeamTactics(),
        "pressing": TeamTactics(tempo=.75, pressing=1, defensive_line=.8),
        "possession": TeamTactics(tempo=.3, width=.7, passing_directness=.1,
                                   crossing=.35, dribbling=.3, shooting=.3, through_balls=.3),
        "direct": TeamTactics(tempo=.8, width=.8, passing_directness=1,
                               crossing=.8, shooting=.65, through_balls=.8),
    }
    if name not in profiles:
        raise ValueError("Unknown tactical preset.")
    return profiles[name]
