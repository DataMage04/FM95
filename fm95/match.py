Warning: truncated output (original token count: 34410)
Total output lines: 2265

"""Match lifecycle and application of resolved football actions."""

from dataclasses import dataclass, field, replace
from enum import Enum
from random import Random

from fm95.actions import ActionConfig, choose_action, resolve_pass, resolve_shot, resolve_dribble, foul_card
from fm95.pitch import CENTRE, Direction, Location, Pitch, Zone
from fm95.statistics import TeamStats, team_statistics
from fm95.attributes import Attributes
from fm95.decisions import (DecisionConfig, DecisionTendencies, apply_decisions,
                            decision_probability)
from fm95.actions import press_win_chance
from fm95.defending import (DefenseConfig, Pressure, defensive_targets,
                            measure_pressure, move_towards)
from fm95.recovery import LooseBall, RecoveryConfig
from fm95.shooting import ShotConfig, blocking_context, rebound_location, rebound_endpoint
from fm95.boundaries import Boundary, BoundaryExit, OutOfPlayConfig, first_exit, misplaced_endpoint
from fm95.crossing import CrossConfig, can_cross, delivery_chance, aerial_chance
from fm95.fatigue import (FatigueConfig, PlayerCondition, tick, movement,
                          movement_factor, effective_attributes)
from fm95.treatment import Treatment
from fm95.rules import PenaltyOffence, PenaltyIncident, penalty_decision, TouchKind, BallTouch
from fm95.attribution import ShotAttribution
from fm95.woodwork import WoodworkConfig, resolve_contact
from fm95.timekeeping import AddedTimeConfig, PeriodTiming
from fm95.set_piece_positions import penalty_positions, clear_attacking_wall
from fm95.restart_positions import restart_positions, clear_distance
from fm95.restart_rules import RestartContext, indirect_location
from fm95.goals import crosses_goal_mouth
from fm95.attacking import AttackConfig, attacking_targets
from fm95.transitions import Transition, TransitionConfig, transition_targets
from fm95.roles import Duty, instructions_for, duty_target
from fm95.tactics import TeamTactics, preference, action_interval, action_preferences, shape_targets, workload
from fm95.injuries import Injury, InjuryConfig, interval_chance, injury_chance
from fm95.substitution_policy import (AutoSubstitutionConfig, SubstitutionRecommendation, recommend,
                                     role_ability, suitability)
from fm95.substitutions import SubstitutionConfig, SubstitutionStatus
from fm95.set_pieces import (SetPieceConfig, can_shoot_free_kick, penalty_mark,
                             goal_centre, resolve_set_piece)
from fm95.offside import OffsideConfig, OffsideSnapshot, snapshot, screening_player
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
    decisions: DecisionTendencies = field(default_factory=DecisionTendencies)

    def __post_init__(self):
        if not isinstance(self.attributes, Attributes):
            raise ValueError("Player attributes must be an Attributes instance.")
        if not isinstance(self.decisions, DecisionTendencies):
            raise ValueError("Player decisions must be a DecisionTendencies instance.")
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
    formation: tuple[tuple[str, Position], ...] | None = None
    duty: Duty | None = None
    last_touch_team_id: str | None = None
    added_seconds: int | None = None
    period: int | None = None
    woodwork_part: str | None = None
    intended_on_target: bool | None = None
    deflector_id: str | None = None
    decision_tendencies: DecisionTendencies | None = None
    shot_choice_probability: float | None = None
    dribble_choice_probability: float | None = None
    cross_choice_probability: float | None = None
    through_ball_choice_probability: float | None = None
    pass_directness: float | None = None
    press_choice_probability: float | None = None


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

    elapsed_seconds is monotonic match time, including opt-in added time.
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
                 home_tactics: TeamTactics | None = None, away_tactics: TeamTactics | None = None,
                 attack_config: AttackConfig | None = None,
                 transition_config: TransitionConfig | None = None,
                 added_time_config: AddedTimeConfig | None = None,
                 woodwork_config: WoodworkConfig | None = None,
                 decision_config: DecisionConfig | None = None):
        if home.id == away.id:
            raise ValueError("A team cannot play itself.")
        if {p.id for p in home.squad} & {p.id for p in away.squad}:
            raise ValueError("A player cannot appear for both teams.")
        home_tactics = home_tactics if home_tactics is not None else TeamTactics()
        away_tactics = away_tactics if away_tactics is not None else TeamTactics()
        if not isinstance(home_tactics, TeamTactics) or not isinstance(away_tactics, TeamTactics):
            raise ValueError("Team instructions must be TeamTactics instances.")
        self.attack_config = attack_config if attack_config is not None else AttackConfig()
        if not isinstance(self.attack_config, AttackConfig):
            raise ValueError("Attacking movement requires an AttackConfig instance.")
        self.transition_config = transition_config if transition_config is not None else TransitionConfig()
        if not isinstance(self.transition_config, TransitionConfig):
            raise ValueError("Transitions require a TransitionConfig instance.")
        self._transition = None
        self._transition_owner = None
        self._restart_context = None
        self.added_time_config = added_time_config if added_time_config is not None else AddedTimeConfig()
        if not isinstance(self.added_time_config, AddedTimeConfig):
            raise ValueError("Added time requires an AddedTimeConfig instance.")
        self._period_number = 1
        self._period_start_seconds = 0
        self._period_lost = {1:0,2:0}
        self._period_minimum = {1:None,2:None}
        self._lost_at_announcement = {1:0,2:0}
        self._restart_delay_remaining = 0
        self._delay_event_cursor = 0
        self.woodwork_config = woodwork_config if woodwork_config is not None else WoodworkConfig()
        if not isinstance(self.woodwork_config,WoodworkConfig):
            raise ValueError("Woodwork requires a WoodworkConfig instance.")
        self._penalty_incident = None
        self._keeper_warnings = {}
        self._keeper_time_counts = {}
        self._last_touch = None
        self._keeper_released = set()
        self._keeper_hand_control = set()
        self._keeper_hold = (None,0)
        self._duties = {}
        self._tactics = {home.id: home_tactics, away.id: away_tactics}
        self.injury_config = injury_config if injury_config is not None else InjuryConfig()
        self._injuries: dict[str, Injury] = {}
        self._treatments = {}
        self._injury_history = {}
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
        self.decision_config = decision_config if decision_config is not None else DecisionConfig()
        if not isinstance(self.decision_config, DecisionConfig):
            raise ValueError("Player decision behavior requires a DecisionConfig instance.")
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
        self._action_elapsed_seconds = self.action_config.inte…26410 tokens truncated….
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
            if self.restart_context is not None:
                self.resolve_restart_exit(exit)
            else:
                self.award_out_of_play(exit, attacking.id, possession.player_id)
            return
        misplaced = (not result.completed and self.recovery_config.enabled
            and self.recovery_config.misplaced_pass_probability > 0
            and self._rng.random() < self.recovery_config.misplaced_pass_probability)
        if result.completed:
            self.record_ball_touch(attacking.id, result.receiver_id, location)
            self._possession = Possession(attacking.id, result.receiver_id, location=location)
        elif not misplaced:
            self.record_ball_touch(defending.id, result.interceptor_id, location)
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
            self._player_locations.update(penalty_positions(attacking.lineup, defending.lineup,
                self._player_locations, possession.player_id, possession.location, direction, self.pitch))
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
            # Clamping near the goal line/touchline must not create an illegal wall.
            for player in wall:
                point = self._player_locations[player.id]
                own_end = 1 if int(direction)==1 else 0
                goal_line = abs(point.x-own_end)<1e-12 and abs(point.y-.5)*self.pitch.width <= self.pitch.goal_width/2
                if not goal_line or self.pitch.distance(point,possession.location)<1:
                    self._player_locations[player.id] = clear_distance(point,possession.location,9.15,self.pitch,-int(direction))
            self._player_locations.update(clear_attacking_wall(attacking.lineup, wall,
                self._player_locations, possession.location, direction, self.pitch))
        self._sync_carrier_location()

    def _play_shot(self, possession: Possession, attacking: TeamInPlay, defending: TeamInPlay,
                   pressure: Pressure, *, header: bool = False,
                   set_piece: str | None = None, period_end=False):
        offside = self._offside_snapshot(possession, attacking, defending)
        goalkeeper = next(p for p in defending.lineup if p.is_goalkeeper)
        shooter = next(p for p in attacking.lineup if p.id == possession.player_id)
        screen=screening_player(offside,possession.location,self._player_locations[goalkeeper.id],
                                self._player_locations,self.pitch,self.offside_config)
        if screen is not None and self.report_offside_involvement(offside,screen,self._player_locations[screen],kind="screening",impact=True):
            return
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
        result,woodwork_part,woodwork_point = resolve_contact(result,self.attacking_direction(attacking.id),
            self.pitch,self._rng,self.woodwork_config)
        if woodwork_part is not None:
            self.events.append(MatchEvent(self.elapsed_seconds,"woodwork_contact",attacking.id,shooter.id,
                woodwork_point.zone,location=woodwork_point,woodwork_part=woodwork_part))
        if self.restart_context is not None and not self.restart_context.permits_direct_goal(attacking.id):
            result = replace(result, goal_probability=0)
        outcome = result.outcome
        if set_piece=="penalty" and self._adjudicate_penalty(outcome,possession,attacking,defending):return
        shot_event_index=len(self.events)
        self.events.append(MatchEvent(
            self.elapsed_seconds, outcome, attacking.id, possession.player_id,
            possession.zone, origin=possession.zone, goalkeeper_id=goalkeeper.id,
            on_target_probability=result.on_target_probability,
            goal_probability=result.goal_probability,
            intended_on_target=result.intended_on_target,
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
        if outcome == "shot_woodwork":
            distance=self.woodwork_config.rebound_distance
            x=woodwork_point.x-int(self.attacking_direction(attacking.id))*distance/self.pitch.length
            y=woodwork_point.y+(self._rng.random()-.5)*distance/self.pitch.width
            exit=first_exit(woodwork_point,x,y) if self.out_config.enabled else None
            if exit is not None:
                self.award_out_of_play(exit,attacking.id,shooter.id)
            else:
                self.set_loose_ball(Location(max(0,min(1,x)),max(0,min(1,y))),reason="woodwork_rebound",offside=offside)
            return
        if outcome in ("shot_blocked", "shot_parried"):
            self.record_ball_touch(defending.id, blocker_id if outcome == "shot_blocked" else goalkeeper.id, possession.location)
            if outcome == "shot_blocked":
                origin = self._player_locations[blocker_id]
            else:
                origin = self._player_locations[goalkeeper.id]
            if self.out_config.enabled:
                x, y = rebound_endpoint(origin, self.pitch, self._rng, self.shot_config.rebound_distance)
                exit = first_exit(origin, x, y)
                if exit is not None:
                    self.resolve_deflection_exit(exit, defending.id,
                                           blocker_id if outcome == "shot_blocked" else goalkeeper.id,
                                           shot=ShotAttribution(shot_event_index,attacking.id,shooter.id,
                                                               bool(result.intended_on_target)))
                    return
                location = Location(x, y)
            else:
                location = rebound_location(origin, self.pitch, self._rng, self.shot_config.rebound_distance)
            self.set_loose_ball(location, reason="blocked_shot" if outcome == "shot_blocked" else "goalkeeper_parry",
                                offside=offside)
            return
        if outcome == "goal" and self.restart_context is not None and not self.restart_context.permits_direct_goal(attacking.id):
            # The shot event has not scored: replace its result without adding xG.
            self.events[-1] = replace(self.events[-1], kind="shot_missed",
                on_target_probability=0, goal_probability=0, reason="direct_restart_goal_disallowed")
            end_x = 1 if self.attacking_direction(attacking.id) == Direction.RIGHT else 0
            self.resolve_restart_exit(BoundaryExit(Boundary.RIGHT if end_x else Boundary.LEFT, Location(end_x,.5)))
            return
        if outcome == "goal":
            self._credit_goal(attacking.id, period_end=period_end)
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
            self.record_ball_touch(defending.id, goalkeeper.id, location)
            self._possession = Possession(defending.id, goalkeeper.id, location=location)
            if outcome=="shot_saved":self._keeper_hand_control.add(goalkeeper.id)
            if outcome == "shot_missed":
                self.events.append(MatchEvent(self.elapsed_seconds, "goal_kick",
                                              defending.id, goalkeeper.id, zone, location=location))
