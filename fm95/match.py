"""Match lifecycle and application of resolved football actions."""

from dataclasses import dataclass, field, replace
from enum import Enum
from random import Random

from fm95.actions import ActionConfig, choose_action, resolve_pass, resolve_shot, resolve_dribble, foul_card
from fm95.pitch import CENTRE, Direction, Location, Pitch, Zone
from fm95.statistics import TeamStats, team_statistics
from fm95.attributes import Attributes
from fm95.actions import press_win_chance
from fm95.defending import (DefenseConfig, Pressure, defensive_targets,
                            measure_pressure, move_towards)
from fm95.recovery import LooseBall, RecoveryConfig
from fm95.shooting import ShotConfig, blocking_context, rebound_location
from fm95.attributes import ability_multiplier
from fm95.positions import Position, operating_zone, formation_reference_locations


@dataclass(frozen=True)
class Player:
    id: str
    name: str
    is_goalkeeper: bool = False
    attributes: Attributes = field(default_factory=Attributes)
    position: Position | None = None

    def __post_init__(self):
        if not isinstance(self.attributes, Attributes):
            raise ValueError("Player attributes must be an Attributes instance.")
        if self.position is None:
            object.__setattr__(self, "position", Position.GK if self.is_goalkeeper else Position.CM)
        if not isinstance(self.position, Position):
            raise ValueError("Player position must be a Position enum value.")
        if (self.position == Position.GK) != self.is_goalkeeper:
            raise ValueError("Goalkeeper designation and position must agree.")


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
    ABANDONED = "abandoned"


@dataclass(frozen=True)
class TeamInPlay:
    id: str
    name: str
    lineup: tuple[Player, ...]


@dataclass(frozen=True)
class Discipline:
    yellow_cards: int
    sent_off: bool


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
    defender_id: str | None = None
    dribble_success_probability: float | None = None
    carrier_dribbling: float | None = None
    defender_tackling: float | None = None
    fouled_player_id: str | None = None
    foul_probability: float | None = None
    reason: str | None = None
    location: Location | None = None
    origin_location: Location | None = None
    pressure: float = 0
    pressing_player_id: str | None = None
    opponent_player_id: str | None = None
    challenge_win_probability: float | None = None
    recovery_candidates: int | None = None
    blocking_player_id: str | None = None
    block_probability: float = 0


@dataclass(frozen=True, init=False)
class Possession:
    """One coherent ownership record; None on Match means no active possession."""

    team_id: str
    player_id: str
    location: Location

    def __init__(self, team_id: str, player_id: str, zone: Zone | None = None,
                 *, location: Location | None = None):
        if location is None:
            if not isinstance(zone, Zone):
                raise ValueError("Possession needs a zone or location.")
            location = Location.centre_of(zone)
        if not isinstance(location, Location) or (zone is not None and location.zone != zone):
            raise ValueError("Possession location must agree with its zone.")
        object.__setattr__(self, "team_id", team_id)
        object.__setattr__(self, "player_id", player_id)
        object.__setattr__(self, "location", location)

    @property
    def zone(self) -> Zone:
        return self.location.zone


@dataclass(frozen=True)
class Restart:
    kind: str
    team_id: str
    taker_id: str
    zone: Zone
    location: Location | None = None

    def __post_init__(self):
        if self.location is None:
            object.__setattr__(self, "location", Location.centre_of(self.zone))
        if not isinstance(self.location, Location) or self.location.zone != self.zone:
            raise ValueError("Restart location must agree with its zone.")


class Match:
    """Advance one simulated second per step; halftime requires explicit resume.

    elapsed_seconds counts match time only. No added time is modelled yet.
    Home kicks off the first half and away kicks off the second half.
    """

    HALF_SECONDS = 45 * 60

    def __init__(self, home: Team, away: Team, *, seed: int | None = None,
                 action_config: ActionConfig | None = None, pitch: Pitch | None = None,
                 defense_config: DefenseConfig | None = None,
                 recovery_config: RecoveryConfig | None = None,
                 shot_config: ShotConfig | None = None):
        if home.id == away.id:
            raise ValueError("A team cannot play itself.")
        if {p.id for p in home.lineup} & {p.id for p in away.lineup}:
            raise ValueError("A player cannot appear for both teams.")
        self.home = home
        self.away = away
        self.pitch = pitch if pitch is not None else Pitch()
        self.defense_config = defense_config if defense_config is not None else DefenseConfig()
        self.recovery_config = recovery_config if recovery_config is not None else RecoveryConfig()
        self.shot_config = shot_config if shot_config is not None else ShotConfig()
        self.phase = Phase.PRE_MATCH
        self.elapsed_seconds = 0
        self.home_goals = 0
        self.away_goals = 0
        self.events: list[MatchEvent] = []
        self._possession: Possession | None = None
        self._loose_ball: LooseBall | None = None
        self._loose_ball_seconds = 0
        self._ends_switched = False
        self._rng = Random(seed)
        self.action_config = action_config if action_config is not None else ActionConfig()
        self._seconds_since_action = 0
        self._possession_seconds = {home.id: 0, away.id: 0}
        self._pending_restart: Restart | None = None
        self._yellow_cards: dict[str, int] = {}
        self._dismissed: set[str] = set()
        self._emergency_keepers: dict[str, str] = {}
        self._player_locations: dict[str, Location] = {}
        self._reset_player_locations()

    @property
    def loose_ball(self) -> LooseBall | None:
        return self._loose_ball

    @property
    def loose_ball_seconds(self) -> int:
        return self._loose_ball_seconds

    def set_loose_ball(self, location: Location, *, reason: str = "development_override"):
        """Release control at an exact location; also supports deterministic scenarios."""
        if self.phase not in (Phase.FIRST_HALF, Phase.SECOND_HALF):
            raise RuntimeError("A loose ball can be created only during play.")
        if not isinstance(location, Location):
            raise ValueError("Loose ball needs a valid Location.")
        old = self._possession
        self._sync_carrier_location()
        self._loose_ball = LooseBall(location, old.team_id if old else None,
                                     old.player_id if old else None, reason)
        self._possession = None
        self._pending_restart = None
        self.events.append(MatchEvent(self.elapsed_seconds, "ball_loose",
            self._loose_ball.last_team_id, self._loose_ball.last_player_id,
            location.zone, location=location, reason=reason))

    def _recover_loose_ball(self):
        loose, config = self._loose_ball, self.recovery_config
        entrants = []
        before = {}
        for team in (self.home, self.away):
            players = [p for p in self.active_players(team.id) if not p.is_goalkeeper
                       or self.pitch.in_penalty_area(loose.location, self.attacking_direction(team.id))]
            for player in players:
                before[player.id] = self.pitch.distance(self._player_locations[player.id], loose.location)
                entrants.append((team.id, player))
            chaser = min(players, key=lambda p: before[p.id])
            self._player_locations[chaser.id] = move_towards(self._player_locations[chaser.id],
                loose.location, config.movement_speed*self.action_config.interval_seconds, self.pitch)
        eligible = [(team_id, player) for team_id, player in entrants
                    if self.pitch.distance(self._player_locations[player.id], loose.location)
                    <= config.control_radius + 1e-9]
        if not eligible:
            self.events.append(MatchEvent(self.elapsed_seconds, "ball_unrecovered", zone=loose.location.zone,
                                          location=loose.location, recovery_candidates=0))
            return
        # Initial proximity rewards earlier arrival; dribbling represents control in this prototype.
        winner_team, winner = self._rng.choices(eligible, weights=[
            ability_multiplier(player.attributes.dribbling-.5, self.action_config.attribute_strength)
            / (1+before[player.id]) for _, player in eligible], k=1)[0]
        self._possession = Possession(winner_team, winner.id, location=loose.location)
        self._loose_ball = None
        self.events.append(MatchEvent(self.elapsed_seconds, "ball_recovered", winner_team, winner.id,
            loose.location.zone, location=loose.location, reason=loose.reason,
            recovery_candidates=len(eligible)))

    def _tackle_knocks_loose(self) -> bool:
        config = self.recovery_config
        return (config.enabled and config.tackle_loose_probability > 0
                and self._rng.random() < config.tackle_loose_probability)

    def _reset_player_locations(self):
        self._player_locations = {player_id: point for team in (self.home, self.away)
                                  for player_id, point in self.formation_reference_locations(team.id).items()}

    def player_locations(self, team_id: str) -> dict[str, Location]:
        """Snapshot of discrete player positions; carrier follows abstract ball endpoints."""
        result = {p.id: self._player_locations[p.id] for p in self.active_players(team_id)}
        if self._possession is not None and self._possession.team_id == team_id:
            result[self._possession.player_id] = self._possession.location
        return result

    def _sync_carrier_location(self):
        if self._possession is not None:
            self._player_locations[self._possession.player_id] = self._possession.location

    def _update_defensive_positions(self, attacking: TeamInPlay, defending: TeamInPlay):
        self._sync_carrier_location()
        if not self.defense_config.enabled:
            return
        config = self.defense_config
        ball = self._possession.location
        anchors = self.formation_reference_locations(defending.id)
        targets = defensive_targets(defending.lineup, attacking.lineup, self._player_locations,
            anchors, self._possession.player_id, ball, self.attacking_direction(defending.id),
            self.pitch, config)
        targets.update(self.formation_reference_locations(attacking.id))
        for player in attacking.lineup + defending.lineup:
            if player.id != self._possession.player_id:
                self._player_locations[player.id] = move_towards(self._player_locations[player.id],
                    targets[player.id], config.movement_speed*self.action_config.interval_seconds, self.pitch)

    def pressure_on_ball(self) -> Pressure:
        if self._possession is None or self._pending_restart is not None:
            return Pressure(None, None, 0)
        attacking = self._active_team(self._possession.team_id)
        if next(p for p in attacking.lineup if p.id == self._possession.player_id).is_goalkeeper:
            return Pressure(None, None, 0)  # Held keeper distribution remains protected for now.
        defending_id = self.away.id if attacking.id == self.home.id else self.home.id
        return measure_pressure(self.active_players(defending_id), self._player_locations,
                                self._possession.location, self.pitch, self.defense_config)

    def _award_foul(self, possession, attacking, defending, defender_id, reason):
        self.events.append(MatchEvent(self.elapsed_seconds, "foul", defending.id, defender_id,
            possession.zone, fouled_player_id=possession.player_id,
            foul_probability=self.action_config.foul_probability,
            location=possession.location, reason=reason))
        card = foul_card(self._rng, self.action_config)
        if card is not None:
            self.issue_card(defending.id, defender_id, card)
            if self.phase == Phase.ABANDONED:
                return
        self._pending_restart = Restart("free_kick", attacking.id, possession.player_id,
                                        possession.zone, possession.location)
        self.events.append(MatchEvent(self.elapsed_seconds, "free_kick_awarded", attacking.id,
                                      possession.player_id, possession.zone, location=possession.location))

    def _try_press(self, possession, attacking, defending, pressure) -> tuple[bool, bool]:
        """Return (carrier action stopped, clean press attempted)."""
        config = self.defense_config
        if (not config.enabled or pressure.defender_id is None or pressure.distance > config.challenge_radius
                or config.press_attempt_probability == 0
                or self._rng.random() >= config.press_attempt_probability):
            return False, False
        defender = next(p for p in defending.lineup if p.id == pressure.defender_id)
        carrier = next(p for p in attacking.lineup if p.id == possession.player_id)
        probability = press_win_chance(defender.attributes.tackling, carrier.attributes.dribbling,
                                       config.press_win_probability, self.action_config.attribute_strength)
        fouled = (self.action_config.foul_probability > 0
                  and self._rng.random() < self.action_config.foul_probability)
        won = False if fouled else self._rng.random() < probability
        knocked_loose = won and self._tackle_knocks_loose()
        self.events.append(MatchEvent(self.elapsed_seconds,
            "press_foul" if fouled else "press_dispossessed" if knocked_loose else "press_won" if won else "press_evaded",
            defending.id, defender.id, possession.zone, location=possession.location,
            opponent_player_id=carrier.id, challenge_win_probability=probability,
            carrier_dribbling=carrier.attributes.dribbling, defender_tackling=defender.attributes.tackling,
            pressure=pressure.intensity))
        if fouled:
            self._award_foul(possession, attacking, defending, defender.id, "press")
            return True, False
        if won:
            if knocked_loose:
                self.set_loose_ball(possession.location, reason="press_dispossession")
                return True, True
            self._possession = Possession(defending.id, defender.id, location=possession.location)
            return True, True
        return False, True

    def discipline(self, team_id: str, player_id: str) -> Discipline:
        if player_id not in {p.id for p in self._team(team_id).lineup}:
            raise ValueError("Player must belong to the selected team.")
        return Discipline(self._yellow_cards.get(player_id, 0), player_id in self._dismissed)

    def active_players(self, team_id: str) -> tuple[Player, ...]:
        team = self._team(team_id)
        return tuple(replace(p, is_goalkeeper=True, position=Position.GK)
                     if p.id == self._emergency_keepers.get(team_id) else p
                     for p in team.lineup if p.id not in self._dismissed)

    def _active_team(self, team_id: str) -> TeamInPlay:
        team = self._team(team_id)
        return TeamInPlay(team.id, team.name, self.active_players(team_id))

    def issue_card(self, team_id: str, player_id: str, card: str):
        """Apply a resolved sanction; also supports deterministic development scenarios."""
        if self.phase not in (Phase.FIRST_HALF, Phase.SECOND_HALF):
            raise RuntimeError("Cards can be issued only during play in this prototype.")
        self.discipline(team_id, player_id)
        if card not in ("yellow", "red"):
            raise ValueError("Card must be 'yellow' or 'red'.")
        if player_id in self._dismissed:
            raise ValueError("Player has already been dismissed.")
        if card == "yellow":
            self._yellow_cards[player_id] = self._yellow_cards.get(player_id, 0) + 1
            self.events.append(MatchEvent(self.elapsed_seconds, "yellow_card", team_id, player_id))
            if self._yellow_cards[player_id] < 2:
                return
        self._dismissed.add(player_id)
        self.events.append(MatchEvent(self.elapsed_seconds, "red_card", team_id, player_id,
                                      reason="second_yellow" if card == "yellow" else "straight_red"))
        if len(self.active_players(team_id)) < 7:
            self.phase = Phase.ABANDONED
            self._possession = None
            self._loose_ball = None
            self._pending_restart = None
            self.events.append(MatchEvent(self.elapsed_seconds, "match_abandoned", team_id,
                                          reason="fewer_than_seven_players"))
            return
        active = self.active_players(team_id)
        if not any(p.is_goalkeeper for p in active):
            replacement = active[0]
            self._emergency_keepers[team_id] = replacement.id
            self.events.append(MatchEvent(self.elapsed_seconds, "goalkeeper_changed", team_id,
                                          replacement.id, reason="emergency_after_dismissal"))
            active = self.active_players(team_id)
        if self._possession is not None and self._possession.player_id == player_id:
            replacement = next(p for p in active if not p.is_goalkeeper)
            self._possession = Possession(team_id, replacement.id, location=self._possession.location)
            if self._pending_restart is not None:
                self._pending_restart = replace(self._pending_restart, taker_id=replacement.id)

    @property
    def pending_restart(self) -> Restart | None:
        return self._pending_restart

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

    def player_operating_zone(self, team_id: str, player_id: str) -> Zone:
        team = self._team(team_id)
        player = next((p for p in self.active_players(team.id) if p.id == player_id), None)
        if player is None:
            raise ValueError("Player must belong to the selected team.")
        return operating_zone(player.position, self.attacking_direction(team_id))

    def formation_reference_locations(self, team_id: str) -> dict[str, Location]:
        """Static formation targets, not actual moving-player coordinates."""
        return formation_reference_locations(self.active_players(team_id), self.attacking_direction(team_id))

    @property
    def ball_location(self) -> Location | None:
        return (self._possession.location if self._possession is not None else
                self._loose_ball.location if self._loose_ball is not None else None)

    def _team(self, team_id: str) -> Team:
        for team in (self.home, self.away):
            if team.id == team_id:
                return team
        raise ValueError(f"Unknown match team: {team_id}")

    def set_possession(self, team_id: str, player_id: str, zone: Zone | None = None,
                       *, location: Location | None = None):
        """Apply an action's resolved ownership/location; does not decide its success.

        Passing and tackling will call this after resolving their outcomes.
        Validation happens before mutation, so rejected changes leave state intact.
        """
        if self.phase not in (Phase.FIRST_HALF, Phase.SECOND_HALF):
            raise RuntimeError("Possession can change only during play.")
        team = self._team(team_id)
        if player_id not in {player.id for player in self.active_players(team.id)}:
            raise ValueError("The ball carrier must be in the possessing team's lineup.")
        possession = Possession(team_id, player_id, zone, location=location)
        self._possession = possession
        self._loose_ball = None
        self._sync_carrier_location()
        self._pending_restart = None
        self.events.append(MatchEvent(self.elapsed_seconds, "possession", team_id,
                                      player_id, possession.zone, location=possession.location))

    def _kickoff(self, team: Team):
        team = self._active_team(team.id)
        taker = next((player for player in team.lineup if player.position == Position.ST),
                     next(player for player in team.lineup if not player.is_goalkeeper))
        self._possession = Possession(team.id, taker.id, CENTRE)
        self._loose_ball = None
        self._pending_restart = None
        self._seconds_since_action = 0
        self._reset_player_locations()
        self._sync_carrier_location()
        self.events.append(MatchEvent(self.elapsed_seconds, "kickoff", team.id,
                                      taker.id, CENTRE, location=self._possession.location))

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
        elif self._loose_ball is not None:
            self._loose_ball_seconds += 1
        self.elapsed_seconds += 1
        if self.phase == Phase.FIRST_HALF and self.elapsed_seconds == self.HALF_SECONDS:
            self.phase = Phase.HALF_TIME
            self._possession = None
            self._loose_ball = None
            self._pending_restart = None
            self.events.append(MatchEvent(self.elapsed_seconds, "half_time"))
        elif self.elapsed_seconds == 2 * self.HALF_SECONDS:
            self.phase = Phase.FULL_TIME
            self._possession = None
            self._loose_ball = None
            self._pending_restart = None
            self.events.append(MatchEvent(self.elapsed_seconds, "full_time"))
        else:
            self._seconds_since_action += 1
            if self._seconds_since_action >= self.action_config.interval_seconds:
                self._play_action()
                self._sync_carrier_location()
                self._seconds_since_action = 0

    def _play_action(self):
        if self._loose_ball is not None:
            self._recover_loose_ball()
            return
        possession = self._possession
        if possession is None:
            raise RuntimeError("An action requires active possession.")
        attacking = self._active_team(possession.team_id)
        defending = self._active_team(self.away.id if attacking.id == self.home.id else self.home.id)
        carrier = next(p for p in attacking.lineup if p.id == possession.player_id)
        pressure = Pressure(None, None, 0)
        if self._pending_restart is not None:
            restart = self._pending_restart
            self._pending_restart = None
            self.events.append(MatchEvent(self.elapsed_seconds, "free_kick_taken",
                                          restart.team_id, restart.taker_id, restart.zone,
                                          location=restart.location))
            action = "pass"  # Initial free kicks are short restarts, not open-play take-ons.
        else:
            self._update_defensive_positions(attacking, defending)
            pressure = self.pressure_on_ball()
            stopped, attempted = self._try_press(possession, attacking, defending, pressure)
            if stopped:
                return
            action = choose_action(possession.zone, self.attacking_direction(attacking.id),
                                   self._rng, self.action_config,
                                   can_dribble=not carrier.is_goalkeeper and not attempted)
        if action == "shot":
            self._play_shot(possession, attacking, defending, pressure)
            return
        if action == "dribble":
            result = resolve_dribble(possession, attacking, defending,
                                     self.attacking_direction(attacking.id), self._rng,
                                     self.action_config,
                                     locations=self._player_locations if self.defense_config.enabled else None,
                                     pitch=self.pitch)
            if result.fouled:
                self._award_foul(possession, attacking, defending, result.defender_id, "take_on")
                return
            if not result.completed and self._tackle_knocks_loose():
                self.events.append(MatchEvent(self.elapsed_seconds, "dribble_dispossessed", attacking.id,
                    possession.player_id, possession.zone, origin=possession.zone,
                    defender_id=result.defender_id, dribble_success_probability=result.success_probability,
                    carrier_dribbling=carrier.attributes.dribbling, defender_tackling=result.defender_tackling,
                    location=possession.location, origin_location=possession.location))
                self.set_loose_ball(possession.location, reason="take_on_dispossession")
                return
            zone = result.destination if result.completed else possession.zone
            location = possession.location.shifted_to(zone) if result.completed else possession.location
            self._possession = (Possession(attacking.id, possession.player_id, location=location)
                                if result.completed else Possession(defending.id, result.defender_id,
                                                                    location=location))
            self.events.append(MatchEvent(
                self.elapsed_seconds, "dribble_completed" if result.completed else "dribble_tackled",
                attacking.id, possession.player_id, zone, origin=possession.zone,
                defender_id=result.defender_id, dribble_success_probability=result.success_probability,
                carrier_dribbling=carrier.attributes.dribbling, defender_tackling=result.defender_tackling,
                location=location, origin_location=possession.location,
            ))
            return
        result = resolve_pass(possession, attacking, defending,
                              self.attacking_direction(attacking.id), self._rng,
                              self.action_config, pressure=pressure.intensity,
                              pressure_effect=self.defense_config.pressure_effect,
                              locations=self._player_locations if self.defense_config.enabled else None,
                              pitch=self.pitch)
        # Provisional endpoint inside the chosen zone; no ball flight or player motion yet.
        location = Location((result.zone.column+.05+.90*self._rng.random())/3,
                            (result.zone.lane+.05+.90*self._rng.random())/3)
        misplaced = (not result.completed and self.recovery_config.enabled
            and self.recovery_config.misplaced_pass_probability > 0
            and self._rng.random() < self.recovery_config.misplaced_pass_probability)
        if result.completed:
            self._possession = Possession(attacking.id, result.receiver_id, location=location)
        elif not misplaced:
            self._possession = Possession(defending.id, result.interceptor_id, location=location)
        # One action event records the passer, intended receiver, destination and outcome.
        self.events.append(MatchEvent(
            self.elapsed_seconds, "pass_completed" if result.completed else "pass_loose" if misplaced else "pass_intercepted",
            attacking.id, possession.player_id, result.zone, result.receiver_id,
            None if misplaced else result.interceptor_id, possession.zone,
            completion_probability=result.completion_probability,
            passer_passing=next(p.attributes.passing for p in attacking.lineup
                                if p.id == possession.player_id),
            location=location, origin_location=possession.location,
            pressure=pressure.intensity, pressing_player_id=pressure.defender_id,
        ))
        if misplaced:
            self.set_loose_ball(location, reason="misplaced_pass")

    def _play_shot(self, possession: Possession, attacking: TeamInPlay, defending: TeamInPlay,
                   pressure: Pressure):
        goalkeeper = next(p for p in defending.lineup if p.is_goalkeeper)
        shooter = next(p for p in attacking.lineup if p.id == possession.player_id)
        blocker_id, block_chance = blocking_context(defending.lineup, self._player_locations,
            possession.location, self.attacking_direction(attacking.id), self.pitch, self.shot_config)
        result = resolve_shot(possession.zone, self._rng, self.action_config,
                              finishing=shooter.attributes.finishing,
                              shot_stopping=goalkeeper.attributes.shot_stopping,
                              pressure=pressure.intensity, pressure_effect=self.defense_config.pressure_effect,
                              block_probability=block_chance,
                              parry_probability=self.shot_config.parry_probability if self.shot_config.enabled else 0)
        outcome = result.outcome
        self.events.append(MatchEvent(
            self.elapsed_seconds, outcome, attacking.id, possession.player_id,
            possession.zone, origin=possession.zone, goalkeeper_id=goalkeeper.id,
            on_target_probability=result.on_target_probability,
            goal_probability=result.goal_probability,
            shooter_finishing=shooter.attributes.finishing,
            goalkeeper_shot_stopping=goalkeeper.attributes.shot_stopping,
            location=possession.location, origin_location=possession.location,
            pressure=pressure.intensity, pressing_player_id=pressure.defender_id,
            blocking_player_id=blocker_id, block_probability=result.block_probability,
        ))
        if outcome in ("shot_blocked", "shot_parried"):
            if outcome == "shot_blocked":
                origin = self._player_locations[blocker_id]
            else:
                origin = self._player_locations[goalkeeper.id]
            location = rebound_location(origin, self.pitch, self._rng, self.shot_config.rebound_distance)
            self.set_loose_ball(location, reason="blocked_shot" if outcome == "shot_blocked" else "goalkeeper_parry")
            return
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
            location = Location(.05 if column == 0 else .95, .5)
            self._possession = Possession(defending.id, goalkeeper.id, location=location)
            if outcome == "shot_missed":
                self.events.append(MatchEvent(self.elapsed_seconds, "goal_kick",
                                              defending.id, goalkeeper.id, zone, location=location))
