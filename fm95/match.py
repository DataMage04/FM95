"""Match lifecycle. Football actions will be added independently of the clock."""

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class Player:
    id: str
    name: str
    is_goalkeeper: bool = False


@dataclass(frozen=True)
class Team:
    id: str
    name: str
    lineup: tuple[Player, ...]

    def __post_init__(self):
        if len(self.lineup) != 11:
            raise ValueError("A starting lineup must contain exactly 11 players.")
        if len({p.id for p in self.lineup}) != 11:
            raise ValueError("Players in a lineup must have unique IDs.")
        if sum(p.is_goalkeeper for p in self.lineup) != 1:
            raise ValueError("A starting lineup must contain one goalkeeper.")


class Phase(str, Enum):
    PRE_MATCH = "pre_match"
    FIRST_HALF = "first_half"
    HALF_TIME = "half_time"
    SECOND_HALF = "second_half"
    FULL_TIME = "full_time"


@dataclass(frozen=True)
class MatchEvent:
    elapsed_seconds: int
    kind: str
    team_id: str | None = None


class Match:
    """Advance one simulated second per step; halftime requires explicit resume.

    elapsed_seconds counts match time only. No added time is modelled yet.
    Home kicks off the first half and away kicks off the second half.
    """

    HALF_SECONDS = 45 * 60

    def __init__(self, home: Team, away: Team):
        if home.id == away.id:
            raise ValueError("A team cannot play itself.")
        if {p.id for p in home.lineup} & {p.id for p in away.lineup}:
            raise ValueError("A player cannot appear for both teams.")
        self.home = home
        self.away = away
        self.phase = Phase.PRE_MATCH
        self.elapsed_seconds = 0
        self.home_goals = 0
        self.away_goals = 0
        self.events: list[MatchEvent] = []

    def start(self):
        if self.phase != Phase.PRE_MATCH:
            raise RuntimeError("Only an unstarted match can start.")
        self.phase = Phase.FIRST_HALF
        self.events.append(MatchEvent(0, "kickoff", self.home.id))

    def resume(self):
        if self.phase != Phase.HALF_TIME:
            raise RuntimeError("Only a match at halftime can resume.")
        self.phase = Phase.SECOND_HALF
        self.events.append(MatchEvent(self.elapsed_seconds, "kickoff", self.away.id))

    def step(self):
        if self.phase not in (Phase.FIRST_HALF, Phase.SECOND_HALF):
            raise RuntimeError("The clock can advance only during play.")
        self.elapsed_seconds += 1
        # Future: update football actions here, separately from lifecycle logic.
        if self.phase == Phase.FIRST_HALF and self.elapsed_seconds == self.HALF_SECONDS:
            self.phase = Phase.HALF_TIME
            self.events.append(MatchEvent(self.elapsed_seconds, "half_time"))
        elif self.elapsed_seconds == 2 * self.HALF_SECONDS:
            self.phase = Phase.FULL_TIME
            self.events.append(MatchEvent(self.elapsed_seconds, "full_time"))
