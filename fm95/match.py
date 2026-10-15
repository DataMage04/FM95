"""Match lifecycle and application of resolved football actions."""

from dataclasses import dataclass, field
from enum import Enum
from random import Random

from fm95.actions import ActionConfig, choose_action, resolve_pass, resolve_shot
from fm95.pitch import CENTRE, Direction, Zone
from fm95.statistics import TeamStats, team_statistics
from fm95.attributes import Attributes


@dataclass(frozen=True)
class Player:
    id: str
    name: str
    is_goalkeeper: bool = False
    attributes: Attributes = field(default_factory=Attributes)

    def __post_init__(self):
        if not isinstance(self.attributes, Attributes):
            raise ValueError("Player attributes must be an Attributes instance.")


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
    player_id: str | None = None
    zone: Zone | None = None
    receiver_id: str | None = None
    interceptor_id: str | None = None
    origin: Zone | None = None
    goalkeeper_id: str | None = None
    completion_probability: float | None = None
    on_target_probability: float | None = None
    goal_probability: float | None = None
    passer_passing: float | None = None
    shooter_finishing: float | None = None
    goalkeeper_shot_stopping: float | None = None


@dataclass(frozen=True)
class Possession:
    """One coherent ownership record; None on Match means no active possession."""

    team_id: str
    player_id: str
    zone: Zone


class Match:
    """Advance one simulated second per step; halftime requires explicit resume.

    elapsed_seconds counts match time only. No added time is modelled yet.
    Home kicks off the first half and away kicks off the second half.
    """

    HALF_SECONDS = 45 * 60

    def __init__(self, home: Team, away: Team, *, seed: int | None = None,
                 action_config: ActionConfig | None = None):
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
        self._possession: Possession | None = None
        self._ends_switched = False
        self._rng = Random(seed)
        self.action_config = action_config if action_config is not None else ActionConfig()
        self._seconds_since_action = 0
        self._possession_seconds = {home.id: 0, away.id: 0}

    def statistics(self, team_id: str) -> TeamStats:
        """Return a fresh immutable snapshot; safe before, during and after play."""
        team = self._team(team_id)
        opponent = self.away if team.id == self.home.id else self.home
        return team_statistics(team.id, opponent.id, self.events, self._possession_seconds)

    @property
    def possession(self) -> Possession | None:
        return self._possession

    def attacking_direction(self, team_id: str) -> Direction:
        self._team(team_id)
        right = (team_id == self.home.id) != self._ends_switched
        return Direction.RIGHT if right else Direction.LEFT

    def _team(self, team_id: str) -> Team:
        for team in (self.home, self.away):
            if team.id == team_id:
                return team
        raise ValueError(f"Unknown match team: {team_id}")

    def set_possession(self, team_id: str, player_id: str, zone: Zone):
        """Apply an action's resolved ownership/location; does not decide its success.

        Passing and tackling will call this after resolving their outcomes.
        Validation happens before mutation, so rejected changes leave state intact.
        """
        if self.phase not in (Phase.FIRST_HALF, Phase.SECOND_HALF):
            raise RuntimeError("Possession can change only during play.")
        team = self._team(team_id)
        if player_id not in {player.id for player in team.lineup}:
            raise ValueError("The ball carrier must be in the possessing team's lineup.")
        if not isinstance(zone, Zone):
            raise ValueError("Ball location must be a Zone.")
        self._possession = Possession(team_id, player_id, zone)
        self.events.append(MatchEvent(self.elapsed_seconds, "possession", team_id,
                                      player_id, zone))

    def _kickoff(self, team: Team):
        # Temporary deterministic choice until positions and kickoff selection exist.
        taker = next(player for player in team.lineup if not player.is_goalkeeper)
        self._possession = Possession(team.id, taker.id, CENTRE)
        self._seconds_since_action = 0
        self.events.append(MatchEvent(self.elapsed_seconds, "kickoff", team.id,
                                      taker.id, CENTRE))

    def start(self):
        if self.phase != Phase.PRE_MATCH:
            raise RuntimeError("Only an unstarted match can start.")
        self.phase = Phase.FIRST_HALF
        self._kickoff(self.home)

    def resume(self):
        if self.phase != Phase.HALF_TIME:
            raise RuntimeError("Only a match at halftime can resume.")
        self.phase = Phase.SECOND_HALF
        self._ends_switched = True
        self._kickoff(self.away)

    def step(self):
        if self.phase not in (Phase.FIRST_HALF, Phase.SECOND_HALF):
            raise RuntimeError("The clock can advance only during play.")
        # Credit [t, t+1) to the owner before actions/whistles at t+1.
        if self._possession is not None:
            self._possession_seconds[self._possession.team_id] += 1
        self.elapsed_seconds += 1
        if self.phase == Phase.FIRST_HALF and self.elapsed_seconds == self.HALF_SECONDS:
            self.phase = Phase.HALF_TIME
            self._possession = None
            self.events.append(MatchEvent(self.elapsed_seconds, "half_time"))
        elif self.elapsed_seconds == 2 * self.HALF_SECONDS:
            self.phase = Phase.FULL_TIME
            self._possession = None
            self.events.append(MatchEvent(self.elapsed_seconds, "full_time"))
        else:
            self._seconds_since_action += 1
            if self._seconds_since_action >= self.action_config.interval_seconds:
                self._play_action()
                self._seconds_since_action = 0

    def _play_action(self):
        possession = self._possession
        if possession is None:
            raise RuntimeError("An action requires active possession.")
        attacking = self._team(possession.team_id)
        defending = self.away if attacking.id == self.home.id else self.home
        if choose_action(possession.zone, self.attacking_direction(attacking.id),
                         self._rng, self.action_config) == "shot":
            self._play_shot(possession, attacking, defending)
            return
        result = resolve_pass(possession, attacking, defending,
                              self.attacking_direction(attacking.id), self._rng,
                              self.action_config)
        if result.completed:
            self._possession = Possession(attacking.id, result.receiver_id, result.zone)
        else:
            self._possession = Possession(defending.id, result.interceptor_id, result.zone)
        # One action event records the passer, intended receiver, destination and outcome.
        self.events.append(MatchEvent(
            self.elapsed_seconds, "pass_completed" if result.completed else "pass_intercepted",
            attacking.id, possession.player_id, result.zone, result.receiver_id,
            result.interceptor_id, possession.zone,
            completion_probability=result.completion_probability,
            passer_passing=next(p.attributes.passing for p in attacking.lineup
                                if p.id == possession.player_id),
        ))

    def _play_shot(self, possession: Possession, attacking: Team, defending: Team):
        goalkeeper = next(p for p in defending.lineup if p.is_goalkeeper)
        shooter = next(p for p in attacking.lineup if p.id == possession.player_id)
        result = resolve_shot(possession.zone, self._rng, self.action_config,
                              finishing=shooter.attributes.finishing,
                              shot_stopping=goalkeeper.attributes.shot_stopping)
        outcome = result.outcome
        self.events.append(MatchEvent(
            self.elapsed_seconds, outcome, attacking.id, possession.player_id,
            possession.zone, origin=possession.zone, goalkeeper_id=goalkeeper.id,
            on_target_probability=result.on_target_probability,
            goal_probability=result.goal_probability,
            shooter_finishing=shooter.attributes.finishing,
            goalkeeper_shot_stopping=goalkeeper.attributes.shot_stopping,
        ))
        if outcome == "goal":
            if attacking.id == self.home.id:
                self.home_goals += 1
            else:
                self.away_goals += 1
            self._kickoff(defending)
        else:
            # Held save or instant goal-kick restart in the keeper's defensive zone.
            column = 0 if self.attacking_direction(defending.id) == Direction.RIGHT else 2
            zone = Zone(column, 1)
            self._possession = Possession(defending.id, goalkeeper.id, zone)
            if outcome == "shot_missed":
                self.events.append(MatchEvent(self.elapsed_seconds, "goal_kick",
                                              defending.id, goalkeeper.id, zone))
