"""Reproducible synthetic player and squad generation for early Milestone 2.

Distributions and positional templates are development scaffolding, not real-world
population estimates. No overall rating is created or stored.
"""
from dataclasses import fields
from hashlib import sha256
from random import Random

from fm95.players.attributes import Attributes
from fm95.players.decisions import DecisionTendencies
from fm95.players.model import Player
from fm95.teams.model import Team
from fm95.match.spatial.positions import Position


FORMATION_433 = (Position.GK, Position.RB, Position.CB, Position.CB, Position.LB,
                 Position.DM, Position.CM, Position.CM, Position.ST, Position.RW, Position.LW)
BENCH_7 = (Position.GK, Position.CB, Position.LB, Position.CM,
           Position.AM, Position.RW, Position.ST)

# Position adds aptitude to relevant skills; it does not disable other skills.
POSITION_BONUSES = {
    "keeper": {"shot_stopping": .18, "handling": .18, "passing": -.04,
               "finishing": -.12, "tackling": -.03, "heading": -.08},
    "defender": {"tackling": .12, "heading": .10, "passing": -.02,
                 "finishing": -.08, "crossing": -.02},
    "fullback": {"tackling": .08, "stamina": .06, "crossing": .08,
                 "heading": -.02},
    "midfielder": {"passing": .10, "stamina": .06, "tackling": .01},
    "creator": {"passing": .15, "dribbling": .08, "crossing": .04,
                "tackling": -.06, "heading": -.05},
    "winger": {"dribbling": .12, "crossing": .14, "finishing": .04,
               "heading": -.10, "tackling": -.08},
    "striker": {"finishing": .17, "heading": .10, "dribbling": .04,
                "tackling": -.12, "crossing": -.05},
}

DECISION_TENDENCIES = {
    "keeper": {"shooting": .05, "dribbling": .10, "crossing": .05,
               "through_balls": .05, "passing_directness": .40, "pressing": .05},
    "defender": {"shooting": .20, "dribbling": .30, "crossing": .25,
                 "through_balls": .25, "passing_directness": .55, "pressing": .76},
    "fullback": {"shooting": .30, "dribbling": .60, "crossing": .72,
                 "through_balls": .35, "passing_directness": .55, "pressing": .60},
    "midfielder": {"shooting": .35, "dribbling": .42, "crossing": .30,
                   "through_balls": .50, "passing_directness": .50, "pressing": .57},
    "creator": {"shooting": .48, "dribbling": .58, "crossing": .42,
                "through_balls": .78, "passing_directness": .55, "pressing": .42},
    "winger": {"shooting": .65, "dribbling": .82, "crossing": .82,
               "through_balls": .62, "passing_directness": .58, "pressing": .48},
    "striker": {"shooting": .86, "dribbling": .62, "crossing": .18,
                "through_balls": .40, "passing_directness": .40, "pressing": .52},
}


def _archetype(position):
    return {
        Position.GK: "keeper", Position.CB: "defender",
        Position.LB: "fullback", Position.RB: "fullback",
        Position.DM: "midfielder", Position.CM: "midfielder",
        Position.AM: "creator", Position.LW: "winger",
        Position.RW: "winger", Position.ST: "striker",
    }[position]


def generate_attributes(*, seed, player_id, position, team_strength=.5):
    """Create correlated but non-identical bounded skills for one generated player.

    team_strength is an experiment control for the synthetic squad's mean quality,
    not a player overall rating. Same seed and identifiers always reproduce values.
    """
    if type(seed) is not int:
        raise ValueError("Player-generation seed must be an integer.")
    if not isinstance(position, Position):
        raise ValueError("Position must be a Position value.")
    if (type(team_strength) not in (float, int) or isinstance(team_strength, bool)
            or not 0 <= team_strength <= 1):
        raise ValueError("Synthetic team strength must be between 0 and 1.")
    key = f"{seed}|{player_id}|{position.value}".encode()
    rng = Random(int.from_bytes(sha256(key).digest()[:8], "big"))
    team_mean = .5 + .4*(team_strength-.5)
    shared_player_deviation = rng.gauss(0, .075)
    bonuses = POSITION_BONUSES[_archetype(position)]
    values = {}
    for field in fields(Attributes):
        name = field.name
        # Injury proneness is independent of skill and team strength.
        if name == "injury_proneness":
            centre = .5
            deviation = rng.gauss(0, .18)
        elif name in ("penalties", "free_kicks"):
            # Specialist execution skills vary, but no decision tendency is implied.
            centre = team_mean + bonuses.get(name, 0)
            deviation = rng.gauss(0, .16)
        else:
            centre = team_mean + shared_player_deviation + bonuses.get(name, 0)
            deviation = rng.gauss(0, .10)
        values[name] = max(0.0, min(1.0, centre+deviation))
    return Attributes(**values)


def generate_decisions(*, seed, player_id, position):
    """Generate role-shaped preferences independently from execution attributes."""
    if type(seed) is not int:
        raise ValueError("Player-generation seed must be an integer.")
    if not isinstance(position, Position):
        raise ValueError("Position must be a Position value.")
    key = f"{seed}|{player_id}|{position.value}|decisions".encode()
    rng = Random(int.from_bytes(sha256(key).digest()[:8], "big"))
    centre = DECISION_TENDENCIES[_archetype(position)]
    return DecisionTendencies(**{name: max(0, min(1, mean+rng.gauss(0, .08)))
                                 for name, mean in centre.items()})


def generate_team(team_id, name, *, seed, team_strength=.5, include_bench=True):
    """Generate a stable 4-3-3 squad with optional seven-player bench."""
    if not isinstance(team_id, str) or not team_id.strip() or not isinstance(name, str) or not name.strip():
        raise ValueError("A team ID and display name are required.")
    if type(include_bench) is not bool:
        raise ValueError("include_bench must be boolean.")
    if type(seed) is not int:
        raise ValueError("Team-generation seed must be an integer.")
    positions = FORMATION_433 + (BENCH_7 if include_bench else ())
    players = []
    for index, position in enumerate(positions, 1):
        player_id = f"{team_id}-{index:02d}"
        players.append(Player(player_id, f"{name} Player {index:02d}",
                              is_goalkeeper=position == Position.GK,
                              position=position,
                              attributes=generate_attributes(seed=seed, player_id=player_id,
                                  position=position, team_strength=team_strength),
                              decisions=generate_decisions(seed=seed, player_id=player_id,
                                  position=position)))
    return Team(team_id, name, tuple(players[:11]), tuple(players[11:]))
