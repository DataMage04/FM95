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
from fm95.shooting import ShotConfig, blocking_context, rebound_location, rebound_endpoint
from fm95.boundaries import Boundary, BoundaryExit, OutOfPlayConfig, first_exit, misplaced_endpoint
from fm95.crossing import CrossConfig, can_cross, delivery_chance, aerial_chance
from fm95.fatigue import (FatigueConfig, PlayerCondition, tick, movement,
                          movement_factor, effective_attributes)
from fm95.tactics import TeamTactics, preference, action_interval, action_preferences, shape_targets, workload
from fm95.injuries import Injury, InjuryConfig, interval_chance, injury_chance
from fm95.substitution_policy import (AutoSubstitutionConfig, SubstitutionRecommendation, recommend,
                                     role_ability, suitability)
from fm95.substitutions import SubstitutionConfig, SubstitutionStatus
from fm95.set_pieces import (SetPieceConfig, can_shoot_free_kick, penalty_mark,
                             goal_centre, resolve_set_piece)
from fm95.offside import OffsideConfig, OffsideSnapshot, snapshot
from fm95.through_balls import ThroughBallConfig, forward_runs, completion_chance
from fm95.goalkeeping import KeeperCrossConfig, handling_chance, keeper_can_intervene, punch_endpoint
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
    bench: tuple[Player, ...] = ()

    @property
    def squad(self) -> tuple[Player, ...]:
        return self.lineup + self.bench

    def __post_init__(self):
        object.__setattr__(self, "lineup", tuple(self.lineup))
        object.__setattr__(self, "bench", tuple(self.bench))
        if any(not isinstance(player, Player) for player in self.squad):
            raise ValueError("A match squad must contain Player instances.")
        if len(self.lineup) != 11:
            raise ValueError("A starting lineup must contain exactly 11 players.")
        if len({p.id for p in self.squad}) != len(self.squad):
            raise ValueError("Players in a match squad must have unique IDs.")
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
    exit_boundary: str | None = None
    intended_zone: Zone | None = None
    crosser_crossing: float | None = None
    attacker_heading: float | None = None
    defender_heading: float | None = None
    aerial_win_probability: float | None = None
    shot_type: str | None = None
    shooter_heading: float | None = None
    goalkeeper_handling: float | None = None
    keeper_success_probability: float | None = None
    keeper_claim_probability: float | None = None
    parry_probability: float | None = None
    pass_type: str | None = None
    receiver_start_location: Location | None = None
    intended_location: Location | None = None
    offside_line_x: float | None = None
    set_piece_ability: float | None = None
    outgoing_player_id: str | None = None
    incoming_player_id: str | None = None
    outgoing_energy: float | None = None
    incoming_energy: float | None = None
    automatic: bool = False
    tactics: TeamTactics | None = None


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
                 shot_config: ShotConfig | None = None,
                 out_config: OutOfPlayConfig | None = None,
                 cross_config: CrossConfig | None = None,
                 keeper_cross_config: KeeperCrossConfig | None = None,
                 through_ball_config: ThroughBallConfig | None = None,
                 offside_config: OffsideConfig | None = None,
                 set_piece_config: SetPieceConfig | None = None,
                 substitution_config: SubstitutionConfig | None = None,
                 fatigue_config: FatigueConfig | None = None,
                 auto_substitution_config: AutoSubstitutionConfig | None = None,
                 injury_config: InjuryConfig | None = None,
                 home_tactics: TeamTactics | None = None, away_tactics: TeamTactics | None = None):
        if home.id == away.id:
            raise ValueError("A team cannot play itself.")
        if {p.id for p in home.squad} & {p.id for p in away.squad}:
            raise ValueError("A player cannot appear for both teams.")
        home_tactics = home_tactics if home_tactics is not None else TeamTactics()
        away_tactics = away_tactics if away_tactics is not None else TeamTactics()
        if not isinstance(home_tactics, TeamTactics) or not isinstance(away_tactics, TeamTactics):
            raise ValueError("Team instructions must be TeamTactics instances.")
        self._tactics = {home.id: home_tactics, away.id: away_tactics}
        self.injury_config = injury_config if injury_config is not None else InjuryConfig()
        self._injuries: dict[str, Injury] = {}
        self.auto_substitution_config = auto_substitution_config if auto_substitution_config is not None else AutoSubstitutionConfig()
        self._automatic_substitution_stoppages: set[tuple[str, Phase, int]] = set()
        self.fatigue_config = fatigue_config if fatigue_config is not None else FatigueConfig()
        self.substitution_config = substitution_config if substitution_config is not None else SubstitutionConfig()
        self.home = home
        self.away = away
        self.pitch = pitch if pitch is not None else Pitch()
        self.defense_config = defense_config if defense_config is not None else DefenseConfig()
        self.recovery_config = recovery_config if recovery_config is not None else RecoveryConfig()
        self.shot_config = shot_config if shot_config is not None else ShotConfig()
        self.out_config = out_config if out_config is not None else OutOfPlayConfig()
        self.cross_config = cross_config if cross_config is not None else CrossConfig()
        self.set_piece_config = set_piece_config if set_piece_config is not None else SetPieceConfig()
        self.offside_config = offside_config if offside_config is not None else OffsideConfig()
        self.through_ball_config = through_ball_config if through_ball_config is not None else ThroughBallConfig()
        self.keeper_cross_config = keeper_cross_config if keeper_cross_config is not None else KeeperCrossConfig()
        self.phase = Phase.PRE_MATCH
        self.elapsed_seconds = 0
        self.home_goals = 0
        self.away_goals = 0
        self.events: list[MatchEvent] = []
        self._possession: Possession | None = None
        self._loose_ball: LooseBall | None = None
        self._loose_ball_seconds = 0
        self._dead_ball_seconds = 0
        self._ends_switched = False
        self._rng = Random(seed)
        self.action_config = action_config if action_config is not None else ActionConfig()
        self._seconds_since_action = 0
        self._action_elapsed_seconds = self.action_config.interval_seconds
        self._possession_seconds = {home.id: 0, away.id: 0}
        self._pending_restart: Restart | None = None
        self._yellow_cards: dict[str, int] = {}
        self._dismissed: set[str] = set()
        self._emergency_keepers: dict[str, str] = {}
        self._lineups = {home.id: home.lineup, away.id: away.lineup}
        self._used_substitutes: set[str] = set()
        self._substitution_windows = {home.id: set(), away.id: set()}
        self._stoppage_serial = 0
        self._kickoff_pending = False
        self._conditions = {p.id: PlayerCondition() for p in home.squad + away.squad}
        self._player_locations: dict[str, Location] = {}
        self._reset_player_locations()

    @property
    def loose_ball(self) -> LooseBall | None:
        return self._loose_ball

    @property
    def loose_ball_seconds(self) -> int:
        return self._loose_ball_seconds

    @property
    def dead_ball_seconds(self) -> int:
        return self._dead_ball_seconds

    def award_out_of_play(self, exit: BoundaryExit, last_team_id: str, last_player_id: str):
        """Apply a resolved non-goal exit, also usable for deterministic scenarios."""
        if self.phase not in (Phase.FIRST_HALF, Phase.SECOND_HALF):
            raise RuntimeError("An exit can be awarded only during play.")
        if not isinstance(exit, BoundaryExit):
            raise ValueError("A valid BoundaryExit is required.")
        if last_player_id not in {p.id for p in self.active_players(last_team_id)}:
            raise ValueError("Last touch must identify an active player of the selected team.")
        other_id = self.away.id if last_team_id == self.home.id else self.home.id
        if exit.boundary in (Boundary.BOTTOM, Boundary.TOP):
            kind, winner, point = "throw_in", other_id, exit.location
        else:
            defended_direction = Direction.RIGHT if exit.boundary == Boundary.LEFT else Direction.LEFT
            defending_id = next(team.id for team in (self.home, self.away)
                                if self.attacking_direction(team.id) == defended_direction)
            if last_team_id == defending_id:
                kind, winner = "corner", other_id
                point = Location(exit.location.x, 0 if exit.location.y < .5 else 1)
            else:
                kind, winner = "goal_kick", defending_id
                goal_area_x = 2.75/self.pitch.length
                point = Location(goal_area_x if exit.boundary == Boundary.LEFT else 1-goal_area_x, .5)
        players = self.active_players(winner)
        if kind == "goal_kick":
            taker = next(p for p in players if p.is_goalkeeper)
        else:
            taker = min((p for p in players if not p.is_goalkeeper),
                        key=lambda p: self.pitch.distance(self._player_locations[p.id], point))
        self.events.append(MatchEvent(self.elapsed_seconds, "ball_out", last_team_id, last_player_id,
            exit.location.zone, location=exit.location, exit_boundary=exit.boundary.value))
        self._possession = None
        self._loose_ball = None
        self._stoppage_serial += 1
        self._pending_restart = Restart(kind, winner, taker.id, point.zone, point)
        self.events.append(MatchEvent(self.elapsed_seconds, f"{kind}_awarded", winner, taker.id,
                                      point.zone, location=point))

    def set_loose_ball(self, location: Location, *, reason: str = "development_override", aerial: bool = False,
                       offside: OffsideSnapshot | None = None):
        """Release control at an exact location; also supports deterministic scenarios."""
        if self.phase not in (Phase.FIRST_HALF, Phase.SECOND_HALF):
            raise RuntimeError("A loose ball can be created only during play.")
        if not isinstance(location, Location):
            raise ValueError("Loose ball needs a valid Location.")
        old = self._possession
        if type(aerial) is not bool or (aerial and old is None):
            raise ValueError("An aerial delivery requires a controlling crosser.")
        self._kickoff_pending = False
        self._sync_carrier_location()
        self._loose_ball = LooseBall(location, old.team_id if old else None,
                                     old.player_id if old else None, reason, "aerial" if aerial else "ground", offside)
        self._possession = None
        self._pending_restart = None
        self.events.append(MatchEvent(self.elapsed_seconds, "ball_loose",
            self._loose_ball.last_team_id, self._loose_ball.last_player_id,
            location.zone, location=location, reason=reason))

    def _offside_snapshot(self, possession, attacking, defending, restart_kind=None):
        if not self.offside_config.enabled or restart_kind in ("goal_kick", "throw_in", "corner"):
            return None
        return snapshot(attacking.id, possession.player_id, possession.location,
                        attacking.lineup, defending.lineup, self._player_locations,
                        self.attacking_direction(attacking.id))

    def _check_offside(self, context, player_id, location):
        if context is None or context.position(player_id) is None:
            return False
        defending_id = self.away.id if context.team_id == self.home.id else self.home.id
        taker = min(self.active_players(defending_id),
                    key=lambda p: self.pitch.distance(self._player_locations[p.id], location))
        self.events.append(MatchEvent(self.elapsed_seconds, "offside", context.team_id, player_id,
            location.zone, location=location, origin=context.ball_location.zone,
            origin_location=context.ball_location,
            receiver_start_location=context.position(player_id), offside_line_x=context.defender_line_x))
        self._possession = None
        self._loose_ball = None
        self._stoppage_serial += 1
        self._pending_restart = Restart("indirect_free_kick", defending_id, taker.id, location.zone, location)
        self.events.append(MatchEvent(self.elapsed_seconds, "indirect_free_kick_awarded", defending_id,
                                      taker.id, location.zone, location=location, reason="offside"))
        return True

    def _play_cross(self, possession, attacking, defending, pressure, offside=None):
        crosser = next(p for p in attacking.lineup if p.id == possession.player_id)
        direction = self.attacking_direction(attacking.id)
        point = Location(.84+.10*self._rng.random(), .38+.24*self._rng.random())
        if direction == Direction.LEFT:
            point = point.rotated()
        chance = delivery_chance(crosser.attributes.crossing, pressure.intensity,
            self.action_config.attribute_strength, self.defense_config.pressure_effect, self.cross_config)
        delivered = self._rng.random() < chance
        exit = None
        if (not delivered and self.out_config.enabled and self.cross_config.failed_cross_out_probability > 0
                and self._rng.random() < self.cross_config.failed_cross_out_probability):
            x, y = misplaced_endpoint(point, self._rng)
            exit = first_exit(possession.location, x, y)
        endpoint = exit.location if exit is not None else point
        self.events.append(MatchEvent(self.elapsed_seconds,
            "cross_delivered" if delivered else "cross_out" if exit else "cross_loose", attacking.id,
            crosser.id, endpoint.zone, location=endpoint, origin=possession.zone,
            origin_location=possession.location, completion_probability=chance,
            crosser_crossing=crosser.attributes.crossing, pressure=pressure.intensity,
            pressing_player_id=pressure.defender_id))
        if exit is not None:
            self.award_out_of_play(exit, attacking.id, crosser.id)
        else:
            self.set_loose_ball(point, reason="cross_delivery" if delivered else "poor_cross", aerial=delivered, offside=offside)

    def _try_keeper_cross(self, ball, defending) -> bool:
        keeper = next(p for p in defending.lineup if p.is_goalkeeper)
        config = replace(self.keeper_cross_config, movement_speed=self.keeper_cross_config.movement_speed
                         * self._movement_factor(keeper.id))
        origin = self._player_locations[keeper.id]
        direction = self.attacking_direction(defending.id)
        if (not keeper_can_intervene(origin, ball.location, direction, self.pitch,
                                    self._action_elapsed_seconds, config)
                or config.attempt_probability == 0 or self._rng.random() >= config.attempt_probability):
            return False
        point = move_towards(origin, ball.location, config.movement_speed*self._action_elapsed_seconds, self.pitch)
        self._player_locations[keeper.id] = point
        self._record_run(keeper, origin, point)
        success_chance = handling_chance(config.success_probability, keeper.attributes.handling,
                                         self.action_config.attribute_strength)
        claim_chance = handling_chance(config.claim_probability, keeper.attributes.handling,
                                       self.action_config.attribute_strength)
        success = self._rng.random() < success_chance
        claimed = success and self._rng.random() < claim_chance
        self.events.append(MatchEvent(self.elapsed_seconds,
            "keeper_cross_missed" if not success else "keeper_cross_claimed" if claimed else "keeper_cross_punched",
            defending.id, keeper.id, ball.location.zone, location=ball.location, goalkeeper_id=keeper.id,
            goalkeeper_handling=keeper.attributes.handling, keeper_success_probability=success_chance,
            keeper_claim_probability=claim_chance))
        if not success:
            return False  # Outfield aerial duel still resolves in this action.
        self._loose_ball = None
        self._possession = Possession(defending.id, keeper.id, location=ball.location)
        self._player_locations[keeper.id] = ball.location  # Abstract hand-contact endpoint.
        if claimed:
            return True
        x, y = punch_endpoint(ball.location, direction, self.pitch, self._rng, config.punch_distance)
        exit = first_exit(ball.location, x, y) if self.out_config.enabled else None
        if exit is not None:
            self.award_out_of_play(exit, defending.id, keeper.id)
        else:
            point = Location(max(0, min(1, x)), max(0, min(1, y)))
            self.set_loose_ball(point, reason="goalkeeper_punch")
        return True

    def _resolve_aerial_ball(self):
        ball = self._loose_ball
        attacking = self._active_team(ball.last_team_id)
        defending = self._active_team(self.away.id if attacking.id == self.home.id else self.home.id)
        if self._try_keeper_cross(ball, defending):
            return
        attackers = [p for p in attacking.lineup if not p.is_goalkeeper and p.id != ball.last_player_id]
        defenders = [p for p in defending.lineup if not p.is_goalkeeper]
        def select(players):
            return self._rng.choices(players, weights=[
                1/(1+self.pitch.distance(self._player_locations[p.id], ball.location)/10)**2
                for p in players], k=1)[0]
        attacker, defender = select(attackers), select(defenders)
        # Contesting a defender is active involvement even if the attacker loses.
        if self._check_offside(ball.offside, attacker.id, ball.location):
            return
        chance = aerial_chance(attacker.attributes.heading, defender.attributes.heading,
                               self.action_config.attribute_strength, self.cross_config)
        attack_won = self._rng.random() < chance
        winner, loser = (attacker, defender) if attack_won else (defender, attacker)
        team_id = attacking.id if attack_won else defending.id
        # Abstract contact points, consistent with existing pass endpoint relocation.
        self._player_locations[attacker.id] = ball.location
        self._player_locations[defender.id] = ball.location
        self._loose_ball = None
        self._possession = Possession(team_id, winner.id, location=ball.location)
        self.events.append(MatchEvent(self.elapsed_seconds, "aerial_won", team_id, winner.id,
            ball.location.zone, opponent_player_id=loser.id, location=ball.location,
            attacker_heading=attacker.attributes.heading, defender_heading=defender.attributes.heading,
            aerial_win_probability=chance))
        if attack_won:
            self._play_shot(self._possession, attacking, defending, self.pressure_on_ball(), header=True)
            return
        self.events.append(MatchEvent(self.elapsed_seconds, "headed_clearance", defending.id, defender.id,
                                      ball.location.zone, location=ball.location))
        distance = self.cross_config.clearance_distance*(.5+.5*self._rng.random())
        x = ball.location.x+int(self.attacking_direction(defending.id))*distance/self.pitch.length
        y = ball.location.y+(self._rng.random()-.5)*distance/self.pitch.width
        exit = first_exit(ball.location, x, y) if self.out_config.enabled else None
        if exit is not None:
            self.award_out_of_play(exit, defending.id, defender.id)
        else:
            point = Location(max(0, min(1, x)), max(0, min(1, y)))
            self.set_loose_ball(point, reason="headed_clearance")

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
            self._move_player(chaser, loose.location,
                              config.movement_speed*self._action_elapsed_seconds)
        eligible = [(team_id, player) for team_id, player in entrants
                    if self.pitch.distance(self._player_locations[player.id], loose.location)
                    <= config.control_radius + 1e-9]
        if not eligible:
            self.events.append(MatchEvent(self.elapsed_seconds, "ball_unrecovered", zone=loose.location.zone,
                                          location=loose.location, recovery_candidates=0))
            return
        # Initial proximity rewards earlier arrival; dribbling represents control in this prototype.
        winner_team, winner = self._rng.choices(eligible, weights=[
            ability_multiplier(self._effective_player(player).attributes.dribbling-.5, self.action_config.attribute_strength)
            / (1+before[player.id]) for _, player in eligible], k=1)[0]
        if (loose.offside is not None and winner_team == loose.offside.team_id
                and self._check_offside(loose.offside, winner.id, loose.location)):
            return
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
                self._move_player(player, targets[player.id],
                                  config.movement_speed*self._action_elapsed_seconds)

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
        kind, point, taker_id = "free_kick", possession.location, possession.player_id
        if self.set_piece_config.enabled:
            direction = self.attacking_direction(attacking.id)
            if self.pitch.in_penalty_area(point, self.attacking_direction(defending.id)):
                kind, point = "penalty", penalty_mark(self.pitch, direction)
            if kind == "penalty" or can_shoot_free_kick(point, direction, self.pitch, self.set_piece_config):
                attribute = "penalties" if kind == "penalty" else "free_kicks"
                taker_id = max((p for p in self.active_players(attacking.id) if not p.is_goalkeeper),
                               key=lambda p: getattr(self._effective_player(p).attributes, attribute)).id
            self._possession = None
            self._loose_ball = None
        self._stoppage_serial += 1
        self._pending_restart = Restart(kind, attacking.id, taker_id, point.zone, point)
        self.events.append(MatchEvent(self.elapsed_seconds, f"{kind}_awarded", attacking.id,
                                      taker_id, point.zone, location=point, origin=possession.zone,
                                      origin_location=possession.location))
        if (self.injury_config.enabled and self.injury_config.foul_injury_probability > 0
                and self._rng.random() < injury_chance(self.injury_config.foul_injury_probability,
                    next(p.attributes.injury_proneness for p in self.active_players(attacking.id)
                         if p.id == possession.player_id), self._conditions[possession.player_id].energy,
                    self.action_config.attribute_strength, self.injury_config)):
            self.injure_player(attacking.id, possession.player_id, reason="foul")

    def _try_press(self, possession, attacking, defending, pressure) -> tuple[bool, bool]:
        """Return (carrier action stopped, clean press attempted)."""
        config = self.defense_config
        attempt_chance = preference(config.press_attempt_probability, self.tactics(defending.id).pressing)
        if (not config.enabled or pressure.defender_id is None or pressure.distance > config.challenge_radius
                or config.press_attempt_probability == 0
                or self._rng.random() >= attempt_chance):
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
        if player_id not in {p.id for p in self._team(team_id).squad}:
            raise ValueError("Player must belong to the selected team.")
        return Discipline(self._yellow_cards.get(player_id, 0), player_id in self._dismissed)

    def active_players(self, team_id: str) -> tuple[Player, ...]:
        team = self._team(team_id)
        return tuple(replace(p, is_goalkeeper=True, position=Position.GK)
                     if p.id == self._emergency_keepers.get(team_id) else p
                     for p in self._lineups[team_id] if p.id not in self._dismissed and p.id not in self._injuries)

    @property
    def substitution_stoppage(self) -> bool:
        return (self.phase == Phase.HALF_TIME or
                self.phase in (Phase.FIRST_HALF, Phase.SECOND_HALF)
                and (self._pending_restart is not None or self._kickoff_pending))

    def available_substitutes(self, team_id: str) -> tuple[Player, ...]:
        return tuple(p for p in self._team(team_id).bench
                     if p.id not in self._used_substitutes and p.id not in self._dismissed and p.id not in self._injuries)

    def substitution_status(self, team_id: str) -> SubstitutionStatus:
        team = self._team(team_id)
        used = sum(p.id in self._used_substitutes for p in team.bench)
        windows = len(self._substitution_windows[team_id])
        return SubstitutionStatus(used, self.substitution_config.max_substitutions-used,
                                  windows, self.substitution_config.max_windows-windows)

    def substitute(self, team_id: str, outgoing_id: str, incoming_id: str):
        self.substitute_many(team_id, ((outgoing_id, incoming_id),))

    def substitute_many(self, team_id: str, changes: tuple[tuple[str, str], ...], *, reason: str | None = None, automatic: bool = False):
        """Apply a complete substitution request atomically at a stoppage.

        Incoming outfield players inherit the outgoing tactical role. No return
        substitutions, extra-time allowance, or simulated entry delays yet.
        Separate calls at the same stoppage share one opportunity.
        """
        self._team(team_id)
        if not self.substitution_stoppage:
            raise RuntimeError("Substitutions require a live-match stoppage or halftime.")
        changes = tuple(changes)
        if not changes or any(not isinstance(pair, (tuple, list)) or len(pair) != 2 for pair in changes):
            raise ValueError("Provide one or more outgoing/incoming player pairs.")
        outgoing_ids = [pair[0] for pair in changes]
        incoming_ids = [pair[1] for pair in changes]
        if len(set(outgoing_ids)) != len(changes) or len(set(incoming_ids)) != len(changes):
            raise ValueError("Each outgoing and incoming player may appear only once.")
        active = {p.id: p for p in self.active_players(team_id)}
        for player in self._lineups[team_id]:
            if player.id in self._injuries and player.id not in self._dismissed:
                role = self._injuries[player.id].position
                active[player.id] = replace(player, position=role, is_goalkeeper=role == Position.GK)
        available = {p.id: p for p in self.available_substitutes(team_id)}
        if any(player_id not in active for player_id in outgoing_ids):
            raise ValueError("An outgoing player must be on the team sheet in play or awaiting injury replacement, and not sent off.")
        if any(player_id not in available for player_id in incoming_ids):
            raise ValueError("An incoming player must be an unused, eligible named substitute.")
        status = self.substitution_status(team_id)
        new_window = (self.phase != Phase.HALF_TIME
                      and self._stoppage_serial not in self._substitution_windows[team_id])
        if len(changes) > status.remaining or new_window and status.windows_remaining == 0:
            raise ValueError("Substitution or opportunity limit exceeded.")
        emergency_id = self._emergency_keepers.get(team_id)
        replacements = {}
        restore_keeper_role = False
        for outgoing_id, incoming_id in changes:
            outgoing, incoming = active[outgoing_id], available[incoming_id]
            if outgoing.is_goalkeeper and not incoming.is_goalkeeper:
                if outgoing_id not in self._injuries or emergency_id is None:
                    raise ValueError("A goalkeeper replacement must be a goalkeeper.")
            if incoming.is_goalkeeper and not outgoing.is_goalkeeper:
                if emergency_id is None:
                    raise ValueError("Cannot introduce a second goalkeeper.")
                restore_keeper_role = True
            if incoming.is_goalkeeper and emergency_id is not None:
                restore_keeper_role = True
            position = Position.GK if incoming.is_goalkeeper else outgoing.position
            if outgoing.is_goalkeeper and not incoming.is_goalkeeper:
                position = next(p.position for p in self._lineups[team_id] if p.id == emergency_id)
            replacements[outgoing_id] = replace(incoming, position=position)
        candidate = tuple(replacements.get(p.id, p) for p in self._lineups[team_id])
        clear_emergency = restore_keeper_role or emergency_id in replacements
        keeper_count = sum(p.is_goalkeeper or p.id == (None if clear_emergency else emergency_id)
                           for p in candidate if p.id not in self._dismissed and p.id not in self._injuries)
        if keeper_count != 1:
            raise ValueError("The resulting active team must have exactly one goalkeeper.")
        # All validation is complete; publish the roster, locations and accounting.
        points = {outgoing_id: self._player_locations[outgoing_id] for outgoing_id in outgoing_ids}
        keeper_point = self._player_locations.get(emergency_id) if clear_emergency else None
        self._lineups[team_id] = candidate
        if clear_emergency:
            self._emergency_keepers.pop(team_id, None)
        if new_window:
            self._substitution_windows[team_id].add(self._stoppage_serial)
            self.events.append(MatchEvent(self.elapsed_seconds, "substitution_window", team_id))
        for outgoing_id, incoming_id in changes:
            incoming = replacements[outgoing_id]
            point = keeper_point if incoming.is_goalkeeper and keeper_point is not None else points[outgoing_id]
            self._player_locations.pop(outgoing_id, None)
            self._player_locations[incoming_id] = point
            self._used_substitutes.add(incoming_id)
            if self._possession is not None and self._possession.player_id == outgoing_id:
                self._possession = Possession(team_id, incoming_id, location=self._possession.location)
            if self._pending_restart is not None and self._pending_restart.taker_id == outgoing_id:
                self._pending_restart = replace(self._pending_restart, taker_id=incoming_id)
            self.events.append(MatchEvent(self.elapsed_seconds, "substitution", team_id,
                incoming_id, point.zone, location=point, outgoing_player_id=outgoing_id,
                incoming_player_id=incoming_id, outgoing_energy=self._conditions[outgoing_id].energy,
                incoming_energy=self._conditions[incoming_id].energy, automatic=automatic,
                reason=reason or ("injury" if outgoing_id in self._injuries else
                                  "half_time" if self.phase == Phase.HALF_TIME else "stoppage")))
        if restore_keeper_role and emergency_id not in outgoing_ids:
            self._player_locations[emergency_id] = self.formation_reference_locations(team_id)[emergency_id]
        self._sync_carrier_location()

    def injury(self, team_id: str, player_id: str) -> Injury | None:
        self.condition(team_id, player_id)
        return self._injuries.get(player_id)

    def _ensure_goalkeeper(self, team_id):
        active = self.active_players(team_id)
        if active and not any(p.is_goalkeeper for p in active):
            self._emergency_keepers[team_id] = active[0].id
            self.events.append(MatchEvent(self.elapsed_seconds, "goalkeeper_changed", team_id,
                                          active[0].id, reason="emergency_after_injury"))

    def _check_minimum_players(self, *, allow_injury_replacements=False):
        for team in (self.home, self.away):
            count = len(self.active_players(team.id))
            if count >= 7:
                continue
            if allow_injury_replacements and count+len(self.injury_substitution_recommendations(team.id)) >= 7:
                continue  # Give the manager the current stoppage to restore seven players.
            self.phase = Phase.ABANDONED
            self._possession = self._loose_ball = self._pending_restart = None
            self._kickoff_pending = False
            self.events.append(MatchEvent(self.elapsed_seconds, "match_abandoned", team.id,
                                          reason="fewer_than_seven_players"))
            return False
        return True

    def injure_player(self, team_id: str, player_id: str, *, reason="development_override"):
        """Withdraw an active player for this match; permanent recovery is not modelled.

        Manual managers may replace them before the next step. Otherwise play
        resumes short-handed, or is abandoned if fewer than seven remain.
        """
        if self.phase not in (Phase.FIRST_HALF, Phase.SECOND_HALF):
            raise RuntimeError("Injuries can be recorded only during play.")
        players = {p.id: p for p in self.active_players(team_id)}
        if player_id not in players or not isinstance(reason, str) or not reason:
            raise ValueError("An injury requires an active player and a nonempty reason.")
        player = players[player_id]
        point, ball = self._player_locations[player_id], self.ball_location
        controlling_team = (self._possession.team_id if self._possession else
                            self._loose_ball.last_team_id if self._loose_ball else team_id)
        self._injuries[player_id] = Injury(self.elapsed_seconds, reason, point, player.position)
        self.events.append(MatchEvent(self.elapsed_seconds, "injury", team_id, player_id,
                                      point.zone, location=point, reason=reason))
        self._ensure_goalkeeper(team_id)
        if self._pending_restart is not None:
            if self._pending_restart.taker_id == player_id:
                active = self.active_players(team_id)
                taker = (next(p for p in active if p.is_goalkeeper) if self._pending_restart.kind == "goal_kick" else
                         max(active, key=lambda p: self.effective_attributes(team_id, p.id).penalties)
                         if self._pending_restart.kind == "penalty" else
                         min(active, key=lambda p: self.pitch.distance(self._player_locations[p.id], ball)))
                self._pending_restart = replace(self._pending_restart, taker_id=taker.id)
            if self._possession is not None and self._possession.player_id == player_id:
                self._possession = None  # Legacy held free-kick state becomes a dead-ball restart.
        elif self._kickoff_pending:
            if self._possession is not None and self._possession.player_id == player_id:
                taker = next(p for p in self.active_players(team_id) if not p.is_goalkeeper)
                self._possession = Possession(team_id, taker.id, location=ball)
                self._sync_carrier_location()
        else:
            # Existing fouls/boundary restarts take precedence; otherwise stop for a drop.
            winner = controlling_team or team_id
            for team in (self.home, self.away):
                if self.pitch.in_penalty_area(ball, self.attacking_direction(team.id)):
                    winner = team.id
                    break
            eligible = self.active_players(winner)
            taker = (next(p for p in eligible if p.is_goalkeeper)
                     if self.pitch.in_penalty_area(ball, self.attacking_direction(winner)) else
                     min(eligible, key=lambda p: self.pitch.distance(self._player_locations[p.id], ball)))
            self._possession = self._loose_ball = None
            self._stoppage_serial += 1
            self._pending_restart = Restart("dropped_ball", winner, taker.id, ball.zone, ball)
            self.events.append(MatchEvent(self.elapsed_seconds, "dropped_ball_awarded", winner, taker.id,
                                          ball.zone, location=ball, reason="injury"))
        self._check_minimum_players(allow_injury_replacements=True)

    def injury_substitution_recommendations(self, team_id: str) -> tuple[SubstitutionRecommendation, ...]:
        self._team(team_id)
        if not self.substitution_stoppage:
            return ()
        status = self.substitution_status(team_id)
        if status.remaining == 0 or (self.phase != Phase.HALF_TIME and status.windows_remaining == 0
                and self._stoppage_serial not in self._substitution_windows[team_id]):
            return ()
        injured = [p for p in self._lineups[team_id] if p.id in self._injuries and p.id not in self._dismissed]
        injured.sort(key=lambda p: (self._injuries[p.id].position != Position.GK, self._injuries[p.id].elapsed_seconds, p.id))
        available, decisions = list(self.available_substitutes(team_id)), []
        emergency_id = self._emergency_keepers.get(team_id)
        for outgoing in injured:
            if len(decisions) >= status.remaining:
                break
            role = self._injuries[outgoing.id].position
            choices = [p for p in available if p.is_goalkeeper == (role == Position.GK)]
            if not choices and role == Position.GK and emergency_id is not None:
                role = next(p.position for p in self._lineups[team_id] if p.id == emergency_id)
                choices = [p for p in available if not p.is_goalkeeper]
            if not choices:
                continue
            incoming = min(choices, key=lambda p: (-suitability(role, p.position),
                -role_ability(self.effective_attributes(team_id, p.id), role), p.id))
            fit = suitability(role, incoming.position)
            decisions.append(SubstitutionRecommendation(outgoing.id, incoming.id,
                self._conditions[outgoing.id].energy, self._conditions[incoming.id].energy, fit, 0))
            available.remove(incoming)
        return tuple(decisions)

    def _try_open_play_injury(self):
        config = self.injury_config
        if not config.enabled or config.probability_per_second == 0:
            return False
        players = [(team.id, p) for team in (self.home, self.away) for p in self.active_players(team.id)]
        chances = [interval_chance(self._action_elapsed_seconds, p.attributes.injury_proneness,
                    self._conditions[p.id].energy, self.action_config.attribute_strength, config) for _, p in players]
        no_incident = 1.0
        for chance in chances:
            no_incident *= 1-chance
        if self._rng.random() >= 1-no_incident:
            return False
        team_id, player = self._rng.choices(players, weights=chances, k=1)[0]
        self.injure_player(team_id, player.id, reason="open_play")
        return True

    def substitution_recommendations(self, team_id: str) -> tuple[SubstitutionRecommendation, ...]:
        """Read-only suggestions are also available while automatic control is disabled."""
        self._team(team_id)
        if not self.substitution_stoppage:
            return ()
        key = (team_id, self.phase, self._stoppage_serial)
        if key in self._automatic_substitution_stoppages:
            return ()
        status = self.substitution_status(team_id)
        new_window = self._stoppage_serial not in self._substitution_windows[team_id]
        if status.remaining == 0 or (self.phase != Phase.HALF_TIME and new_window and status.windows_remaining == 0):
            return ()
        return recommend(self.active_players(team_id), self.available_substitutes(team_id),
                         self.conditions(team_id), self.elapsed_seconds, status.remaining,
                         self.auto_substitution_config, self.fatigue_config,
                         halftime=self.phase == Phase.HALF_TIME,
                         protected_id=self._pending_restart.taker_id if self._pending_restart else None)

    def _apply_automatic_substitutions(self):
        if not self.auto_substitution_config.enabled or not self.substitution_stoppage:
            return
        for team in (self.home, self.away):
            forced = self.injury_substitution_recommendations(team.id)
            if forced:
                self.substitute_many(team.id, tuple((d.outgoing_id, d.incoming_id) for d in forced),
                                     reason="injury", automatic=True)
                self._automatic_substitution_stoppages.add((team.id, self.phase, self._stoppage_serial))
                continue
            decisions = self.substitution_recommendations(team.id)
            if decisions:
                self.substitute_many(team.id, tuple((d.outgoing_id, d.incoming_id) for d in decisions),
                                     reason="fatigue", automatic=True)
                self._automatic_substitution_stoppages.add((team.id, self.phase, self._stoppage_serial))

    def condition(self, team_id: str, player_id: str) -> PlayerCondition:
        if player_id not in {p.id for p in self._team(team_id).squad}:
            raise ValueError("Player must belong to the selected team.")
        return self._conditions[player_id]

    def conditions(self, team_id: str) -> dict[str, PlayerCondition]:
        """Independent dictionary of immutable snapshots, including unused substitutes."""
        return {p.id: self._conditions[p.id] for p in self._team(team_id).squad}

    def effective_attributes(self, team_id: str, player_id: str) -> Attributes:
        self.condition(team_id, player_id)
        player = next(p for p in self._team(team_id).squad if p.id == player_id)
        return effective_attributes(player.attributes, self._conditions[player_id].energy, self.fatigue_config)

    def _effective_player(self, player):
        return replace(player, attributes=effective_attributes(
            player.attributes, self._conditions[player.id].energy, self.fatigue_config))

    def _movement_factor(self, player_id):
        return movement_factor(self._conditions[player_id].energy, self.fatigue_config)

    def _record_run(self, player, origin, target):
        self._conditions[player.id] = movement(self._conditions[player.id],
            self.pitch.distance(origin, target), player.attributes.stamina, self.fatigue_config)

    def _move_player(self, player, target, distance):
        origin = self._player_locations[player.id]
        point = move_towards(origin, target, distance*self._movement_factor(player.id), self.pitch)
        self._player_locations[player.id] = point
        self._record_run(player, origin, point)

    def _advance_conditions(self):
        resting = self._pending_restart is not None or self._kickoff_pending
        for team in (self.home, self.away):
            load = workload(self.tactics(team.id), self._possession is not None and self._possession.team_id == team.id)
            for player in self.active_players(team.id):
                self._conditions[player.id] = tick(self._conditions[player.id], player.attributes.stamina,
                    player.is_goalkeeper, resting, self.fatigue_config, load=load)

    def _active_team(self, team_id: str) -> TeamInPlay:
        team = self._team(team_id)
        return TeamInPlay(team.id, team.name, tuple(self._effective_player(p) for p in self.active_players(team_id)))

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
        elif self._pending_restart is not None and self._pending_restart.taker_id == player_id:
            if self._pending_restart.kind == "penalty":
                replacement = max((p for p in active if not p.is_goalkeeper),
                                  key=lambda p: self._effective_player(p).attributes.penalties)
            else:
                replacement = (next(p for p in active if p.is_goalkeeper)
                               if self._pending_restart.kind == "goal_kick" else
                               next(p for p in active if not p.is_goalkeeper))
            self._pending_restart = replace(self._pending_restart, taker_id=replacement.id)

    @property
    def pending_restart(self) -> Restart | None:
        return self._pending_restart

    def statistics(self, team_id: str) -> TeamStats:
        """Return a fresh immutable snapshot; safe before, during and after play."""
        team = self._team(team_id)
        opponent = self.away if team.id == self.home.id else self.home
        return team_statistics(team.id, opponent.id, self.events, self._possession_seconds,
                               conditions=self.conditions(team_id),
                               active_ids=tuple(p.id for p in self.active_players(team_id)))

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

    def tactics(self, team_id: str) -> TeamTactics:
        self._team(team_id)
        return self._tactics[team_id]

    def set_tactics(self, team_id: str, instructions: TeamTactics):
        self._team(team_id)
        if self.phase in (Phase.FULL_TIME, Phase.ABANDONED):
            raise RuntimeError("Tactics cannot change after the match ends.")
        if not isinstance(instructions, TeamTactics):
            raise ValueError("Team instructions must be a TeamTactics instance.")
        if self._tactics[team_id] != instructions:
            self._tactics[team_id] = instructions
            self.events.append(MatchEvent(self.elapsed_seconds, "tactics_changed", team_id, tactics=instructions))

    def current_action_interval(self) -> int:
        if self._possession is None or self._pending_restart is not None or self._kickoff_pending:
            return self.action_config.interval_seconds
        return action_interval(self.action_config.interval_seconds, self.tactics(self._possession.team_id))

    def formation_reference_locations(self, team_id: str) -> dict[str, Location]:
        """Formation targets adjusted by team instructions, distinct from actual locations."""
        players = self.active_players(team_id)
        direction = self.attacking_direction(team_id)
        references = formation_reference_locations(players, direction)
        return shape_targets(players, references, direction, self.tactics(team_id))

    @property
    def ball_location(self) -> Location | None:
        return (self._possession.location if self._possession is not None else
                self._loose_ball.location if self._loose_ball is not None else
                self._pending_restart.location if self._pending_restart is not None else None)

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
        self._kickoff_pending = False
        self._possession = possession
        self._loose_ball = None
        self._sync_carrier_location()
        self._pending_restart = None
        self.events.append(MatchEvent(self.elapsed_seconds, "possession", team_id,
                                      player_id, possession.zone, location=possession.location))

    def _kickoff(self, team: Team):
        self._stoppage_serial += 1
        self._kickoff_pending = True
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
        self._apply_automatic_substitutions()
        if not self._check_minimum_players():
            return
        if self.fatigue_config.enabled:
            for team in (self.home, self.away):
                for player in self.active_players(team.id):
                    state = self._conditions[player.id]
                    self._conditions[player.id] = replace(state,
                        energy=min(1, state.energy+self.fatigue_config.halftime_recovery))
        self.phase = Phase.SECOND_HALF
        self._ends_switched = True
        self._kickoff(self.away)

    def step(self):
        if self.phase not in (Phase.FIRST_HALF, Phase.SECOND_HALF):
            raise RuntimeError("The clock can advance only during play.")
        self._apply_automatic_substitutions()
        if not self._check_minimum_players():
            return
        self._advance_conditions()
        # Credit [t, t+1) to the owner before actions/whistles at t+1.
        if self._possession is not None:
            self._possession_seconds[self._possession.team_id] += 1
        elif self._loose_ball is not None:
            self._loose_ball_seconds += 1
        elif self._pending_restart is not None:
            self._dead_ball_seconds += 1
        self.elapsed_seconds += 1
        # Resolve an awarded penalty before the period ends, even if the normal
        # action interval is not due. The abstract kick finishes at this timestamp.
        if (self.elapsed_seconds in (self.HALF_SECONDS, 2*self.HALF_SECONDS)
                and self._pending_restart is not None and self._pending_restart.kind == "penalty"):
            self._action_elapsed_seconds = max(1, self._seconds_since_action+1)
            self._play_action(period_end=True)
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
            if self._seconds_since_action >= self.current_action_interval():
                self._action_elapsed_seconds = self._seconds_since_action
                self._play_action()
                self._sync_carrier_location()
                self._seconds_since_action = 0

    def _play_action(self, *, period_end=False):
        was_kickoff = self._kickoff_pending
        self._kickoff_pending = False
        if (not was_kickoff and self._pending_restart is None and self._possession is not None
                and self._try_open_play_injury()):
            return
        if self._loose_ball is not None:
            if self._loose_ball.kind == "aerial":
                self._resolve_aerial_ball()
            else:
                self._recover_loose_ball()
            return
        possession = self._possession
        if possession is None and self._pending_restart is not None:
            restart = self._pending_restart
            possession = Possession(restart.team_id, restart.taker_id, location=restart.location)
            self._possession = possession
            self._sync_carrier_location()
        if possession is None:
            raise RuntimeError("An action requires active possession.")
        attacking = self._active_team(possession.team_id)
        defending = self._active_team(self.away.id if attacking.id == self.home.id else self.home.id)
        carrier = next(p for p in attacking.lineup if p.id == possession.player_id)
        pressure = Pressure(None, None, 0)
        restart_kind = self._pending_restart.kind if self._pending_restart else None
        open_play = self._pending_restart is None
        instructions = self.tactics(attacking.id)
        choices = action_preferences(self.action_config, instructions)
        cross_choice = preference(self.cross_config.choice_probability, instructions.crossing)
        through_choice = preference(self.through_ball_config.choice_probability, instructions.through_balls)
        if self._pending_restart is not None:
            restart = self._pending_restart
            self._pending_restart = None
            self.events.append(MatchEvent(self.elapsed_seconds, f"{restart.kind}_taken",
                                          restart.team_id, restart.taker_id, restart.zone,
                                          location=restart.location))
            action = "pass"
            if restart.kind == "penalty":
                self._position_set_piece(possession, attacking, defending, penalty=True)
                self._play_shot(possession, attacking, defending, pressure,
                                set_piece="penalty", period_end=period_end)
                return
            if (restart.kind == "free_kick" and self.set_piece_config.enabled
                    and can_shoot_free_kick(possession.location, self.attacking_direction(attacking.id),
                                           self.pitch, self.set_piece_config)
                    and self.set_piece_config.direct_shot_probability > 0
                    and self._rng.random() < self.set_piece_config.direct_shot_probability):
                self._position_set_piece(possession, attacking, defending, penalty=False)
                self._play_shot(possession, attacking, defending, pressure, set_piece="direct_free_kick")
                return
            if (restart.kind == "corner" and self.cross_config.enabled
                    and self.cross_config.corner_cross_probability > 0
                    and self._rng.random() < self.cross_config.corner_cross_probability):
                action = "cross"
        else:
            self._update_defensive_positions(attacking, defending)
            pressure = self.pressure_on_ball()
            stopped, attempted = self._try_press(possession, attacking, defending, pressure)
            if stopped:
                return
            if (self.cross_config.enabled and not attempted and not carrier.is_goalkeeper
                    and can_cross(possession.location, self.attacking_direction(attacking.id))
                    and self.cross_config.choice_probability > 0
                    and self._rng.random() < cross_choice):
                action = "cross"
            else:
                action = choose_action(possession.zone, self.attacking_direction(attacking.id),
                                   self._rng, choices,
                                   can_dribble=not carrier.is_goalkeeper and not attempted)
        offside = self._offside_snapshot(possession, attacking, defending, restart_kind)
        if action == "cross":
            self._play_cross(possession, attacking, defending, pressure, offside)
            return
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
            target = possession.location.shifted_to(zone) if result.completed else possession.location
            location = move_towards(possession.location, target,
                self.pitch.distance(possession.location, target)*self._movement_factor(carrier.id)
                *self._action_elapsed_seconds/self.action_config.interval_seconds, self.pitch)
            zone = location.zone
            self._record_run(carrier, possession.location, location)
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
                              pitch=self.pitch,
                              directness=instructions.passing_directness if open_play else .5,
                              width=instructions.width if open_play else .5)
        pass_type = "long" if abs(result.zone.column-possession.zone.column) > 1 else "ordinary"
        receiver_start = self._player_locations[result.receiver_id]
        runs = (forward_runs(attacking.lineup, self._player_locations, possession.player_id,
                            possession.location, self.attacking_direction(attacking.id),
                            self.pitch, self.through_ball_config,
                            movement_factors={p.id: self._movement_factor(p.id)*self._action_elapsed_seconds
                                              /self.action_config.interval_seconds for p in attacking.lineup})
                if open_play and not carrier.is_goalkeeper and self.through_ball_config.enabled else [])
        # Resolve an explicit run from the receiver's position at the moment of the pass.
        run = (self._rng.choice(runs) if runs and self.through_ball_config.choice_probability > 0
               and self._rng.random() < through_choice else None)
        # Provisional endpoint inside the chosen zone; no ball flight or player motion yet.
        location = Location((result.zone.column+.05+.90*self._rng.random())/3,
                            (result.zone.lane+.05+.90*self._rng.random())/3)
        if run is not None:
            receiver_id, receiver_start, location = run
            chance = completion_chance(carrier.attributes.passing, pressure.intensity,
                self.action_config.attribute_strength, self.defense_config.pressure_effect,
                self.through_ball_config)
            completed = self._rng.random() < chance
            interceptor = min((p for p in defending.lineup if not p.is_goalkeeper),
                             key=lambda p: self.pitch.distance(self._player_locations[p.id], location))
            result = replace(result, receiver_id=receiver_id, zone=location.zone,
                             completed=completed, interceptor_id=None if completed else interceptor.id,
                             completion_probability=chance)
            pass_type = "through"
            # The runner advances even when delivery fails; ownership resolves below.
            self._player_locations[receiver_id] = location
            runner = next(p for p in attacking.lineup if p.id == receiver_id)
            self._record_run(runner, receiver_start, location)
        intended_location = location
        if result.completed and offside is not None and offside.position(result.receiver_id) is not None:
            self.events.append(MatchEvent(self.elapsed_seconds, "pass_offside", attacking.id,
                possession.player_id, location.zone, receiver_id=result.receiver_id,
                origin=possession.zone, location=location, origin_location=possession.location,
                intended_location=location, intended_zone=result.zone, pass_type=pass_type,
                receiver_start_location=receiver_start, completion_probability=result.completion_probability,
                passer_passing=carrier.attributes.passing, pressure=pressure.intensity,
                pressing_player_id=pressure.defender_id))
            self._check_offside(offside, result.receiver_id, location)
            return
        if (not result.completed and self.out_config.enabled
                and self.out_config.failed_pass_out_probability > 0
                and self._rng.random() < self.out_config.failed_pass_out_probability):
            x, y = misplaced_endpoint(location, self._rng)
            exit = first_exit(possession.location, x, y)
            self.events.append(MatchEvent(self.elapsed_seconds, "pass_out", attacking.id,
                possession.player_id, exit.location.zone, receiver_id=result.receiver_id,
                origin=possession.zone, location=exit.location, origin_location=possession.location,
                completion_probability=result.completion_probability, passer_passing=carrier.attributes.passing,
                intended_zone=result.zone, pass_type=pass_type,
                receiver_start_location=receiver_start, intended_location=intended_location,
                pressure=pressure.intensity, pressing_player_id=pressure.defender_id))
            self.award_out_of_play(exit, attacking.id, possession.player_id)
            return
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
            intended_zone=result.zone, pass_type=pass_type,
            receiver_start_location=receiver_start, intended_location=intended_location,
            passer_passing=next(p.attributes.passing for p in attacking.lineup
                                if p.id == possession.player_id),
            location=location, origin_location=possession.location,
            pressure=pressure.intensity, pressing_player_id=pressure.defender_id,
        ))
        if misplaced:
            self.set_loose_ball(location, reason="misplaced_pass", offside=offside)

    def _position_set_piece(self, possession, attacking, defending, *, penalty):
        direction = self.attacking_direction(attacking.id)
        goal = goal_centre(direction)
        keeper = next(p for p in defending.lineup if p.is_goalkeeper)
        self._player_locations[keeper.id] = goal
        if penalty:
            # Other players start outside the area and behind the mark, >=9.15 m away.
            distance = max(self.pitch.penalty_depth+.1, self.pitch.penalty_depth*2/3+9.15)
            x = max(0, min(1, goal.x-int(direction)*distance/self.pitch.length))
            for player in attacking.lineup + defending.lineup:
                if player.id not in (possession.player_id, keeper.id):
                    current = self._player_locations[player.id]
                    behind_x = min(current.x, x) if direction == Direction.RIGHT else max(current.x, x)
                    self._player_locations[player.id] = Location(behind_x, current.y)
        else:
            # A small provisional wall feeds the existing spatial blocking model.
            ox, oy = self.pitch.metres(possession.location)
            gx, gy = self.pitch.metres(goal)
            distance = max(self.pitch.distance(possession.location, goal), 1e-9)
            dx, dy = (gx-ox)/distance, (gy-oy)/distance
            wall_distance = min(9.15, distance)
            wall = sorted((p for p in defending.lineup if not p.is_goalkeeper),
                          key=lambda p: self.pitch.distance(self._player_locations[p.id], possession.location))[:3]
            for player in defending.lineup:
                if (not player.is_goalkeeper and player not in wall
                        and self.pitch.distance(self._player_locations[player.id], possession.location) < wall_distance):
                    self._player_locations[player.id] = self.pitch.from_metres(
                        max(0, min(self.pitch.length, ox+dx*wall_distance)),
                        max(0, min(self.pitch.width, oy+dy*wall_distance)))
            for index, player in enumerate(wall):
                offset = (index-(len(wall)-1)/2)*.75
                self._player_locations[player.id] = self.pitch.from_metres(
                    max(0, min(self.pitch.length, ox+dx*wall_distance-dy*offset)),
                    max(0, min(self.pitch.width, oy+dy*wall_distance+dx*offset)))
        self._sync_carrier_location()

    def _play_shot(self, possession: Possession, attacking: TeamInPlay, defending: TeamInPlay,
                   pressure: Pressure, *, header: bool = False,
                   set_piece: str | None = None, period_end=False):
        offside = self._offside_snapshot(possession, attacking, defending)
        goalkeeper = next(p for p in defending.lineup if p.is_goalkeeper)
        shooter = next(p for p in attacking.lineup if p.id == possession.player_id)
        blocker_id, block_chance = blocking_context(defending.lineup, self._player_locations,
            possession.location, self.attacking_direction(attacking.id), self.pitch, self.shot_config)
        if set_piece == "penalty":
            blocker_id, block_chance = None, 0
        parry_chance = (handling_chance(self.shot_config.parry_probability,
                        1-goalkeeper.attributes.handling, self.action_config.attribute_strength)
                        if self.shot_config.enabled else 0)
        set_piece_ability = None
        if set_piece is not None:
            set_piece_ability = (shooter.attributes.penalties if set_piece == "penalty"
                                 else shooter.attributes.free_kicks)
            result = resolve_set_piece(possession.location, self.attacking_direction(attacking.id),
                self.pitch, self._rng, self.action_config, self.set_piece_config,
                penalty=set_piece == "penalty", ability=set_piece_ability,
                shot_stopping=goalkeeper.attributes.shot_stopping,
                block_probability=block_chance, parry_probability=parry_chance)
        else:
            result = resolve_shot(possession.zone, self._rng, self.action_config,
                                  finishing=shooter.attributes.finishing,
                                  shot_stopping=goalkeeper.attributes.shot_stopping,
                                  pressure=pressure.intensity, pressure_effect=self.defense_config.pressure_effect,
                                  block_probability=block_chance,
                                  parry_probability=parry_chance,
                                  heading=shooter.attributes.heading if header else None)
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
            shot_type=set_piece or ("header" if header else "foot"),
            set_piece_ability=set_piece_ability,
            shooter_heading=shooter.attributes.heading if header else None,
            goalkeeper_handling=goalkeeper.attributes.handling,
            parry_probability=parry_chance,
        ))
        if period_end and outcome != "goal":
            return  # No follow-up kick is permitted after this period-ending penalty.
        if outcome in ("shot_blocked", "shot_parried"):
            if outcome == "shot_blocked":
                origin = self._player_locations[blocker_id]
            else:
                origin = self._player_locations[goalkeeper.id]
            if self.out_config.enabled:
                x, y = rebound_endpoint(origin, self.pitch, self._rng, self.shot_config.rebound_distance)
                exit = first_exit(origin, x, y)
                if exit is not None:
                    self.award_out_of_play(exit, defending.id,
                                           blocker_id if outcome == "shot_blocked" else goalkeeper.id)
                    return
                location = Location(x, y)
            else:
                location = rebound_location(origin, self.pitch, self._rng, self.shot_config.rebound_distance)
            self.set_loose_ball(location, reason="blocked_shot" if outcome == "shot_blocked" else "goalkeeper_parry",
                                offside=offside)
            return
        if outcome == "goal":
            if attacking.id == self.home.id:
                self.home_goals += 1
            else:
                self.away_goals += 1
            if not period_end:
                self._kickoff(defending)
        else:
            if outcome == "shot_missed" and self.out_config.enabled:
                end_x = 1 if self.attacking_direction(attacking.id) == Direction.RIGHT else 0
                self.award_out_of_play(BoundaryExit(Boundary.RIGHT if end_x else Boundary.LEFT,
                    Location(end_x, .05+.9*self._rng.random())), attacking.id, shooter.id)
                return
            # Held save or instant goal-kick restart in the keeper's defensive zone.
            column = 0 if self.attacking_direction(defending.id) == Direction.RIGHT else 2
            zone = Zone(column, 1)
            location = Location(.05 if column == 0 else .95, .5)
            self._possession = Possession(defending.id, goalkeeper.id, location=location)
            if outcome == "shot_missed":
                self.events.append(MatchEvent(self.elapsed_seconds, "goal_kick",
                                              defending.id, goalkeeper.id, zone, location=location))
