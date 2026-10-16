"""In-memory round-robin competitions built on the match engine."""

from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Callable, Mapping

from fm95.match.simulation import run_match
from fm95.match.engine import Match, Phase
from fm95.teams.model import Team
from fm95.teams.club import Club, SquadSelection
from fm95.competition.manager import Manager, ManagerAssignment, cpu_selection
from fm95.match.statistics import TeamStats
from fm95.match.tactics import TeamTactics


@dataclass(frozen=True)
class Fixture:
    id: str
    matchday: int
    home_team_id: str
    away_team_id: str
    seed: int


@dataclass(frozen=True)
class FixtureResult:
    fixture_id: str
    home_goals: int
    away_goals: int
    home_stats: TeamStats
    away_stats: TeamStats
    elapsed_seconds: int
    home_lineup: tuple[str, ...] = ()
    away_lineup: tuple[str, ...] = ()
    home_tactics: TeamTactics = TeamTactics()
    away_tactics: TeamTactics = TeamTactics()


@dataclass(frozen=True)
class Standing:
    team_id: str
    team_name: str
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int


class Season:
    """A seeded, in-memory home-and-away league season.

    Each fixture stores its own seed, so an individual match can be reproduced
    independently of the order in which other fixtures are run. Results are
    recorded once and standings are derived from those results.
    """

    def __init__(self, name: str, teams: tuple[Team, ...] | list[Team], *, seed: int,
                 points_for_win: int = 3, points_for_draw: int = 1,
                 points_for_loss: int = 0):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Season name must be a non-empty string.")
        if type(seed) is not int:
            raise ValueError("Season seed must be an integer.")
        for label, points in (("win", points_for_win), ("draw", points_for_draw),
                              ("loss", points_for_loss)):
            if type(points) is not int or points < 0:
                raise ValueError(f"Points for {label} must be a non-negative integer.")
        teams = tuple(Club.from_team(team) if isinstance(team, Team) else team for team in teams)
        if len(teams) < 2 or any(not isinstance(team, Club) for team in teams):
            raise ValueError("A season requires at least two Club instances or legacy Team instances.")
        if len({team.id for team in teams}) != len(teams):
            raise ValueError("Season team IDs must be unique.")
        if any(not isinstance(team.id, str) or not team.id.strip()
               or not isinstance(team.name, str) or not team.name.strip() for team in teams):
            raise ValueError("Season teams need non-empty string IDs and names.")
        roster_ids = [player.id for team in teams for player in team.squad]
        if len(set(roster_ids)) != len(roster_ids):
            raise ValueError("A player cannot appear in more than one season squad.")
        self.name = name
        self.season_number = 1
        self.season_history = []
        self.seed = seed
        self.teams = teams
        self.points_for_win = points_for_win
        self.points_for_draw = points_for_draw
        self.points_for_loss = points_for_loss
        self._team_by_id = {team.id: team for team in teams}
        self.fixtures = self._make_fixtures()
        self._fixture_by_id = {fixture.id: fixture for fixture in self.fixtures}
        self._results: dict[str, FixtureResult] = {}
        self._run_settings: dict | None = None
        self.manager_assignment: ManagerAssignment | None = None
        from fm95.squad.operations import SquadOperations
        from fm95.finances.model import ClubFinances
        self.squad_operations = SquadOperations(self.teams)
        self.club_finances = ClubFinances(self.teams)
        self.validate()

    def assign_manager(self, manager: Manager, team_id: str, *,
                       selection: SquadSelection | None = None,
                       tactics: TeamTactics | None = None) -> ManagerAssignment:
        """Assign the offline manager to one club before any fixture is played."""
        if self._results or self._run_settings is not None:
            raise ValueError("Manager assignment must be set before the first fixture.")
        if not isinstance(manager, Manager):
            raise ValueError("manager must be a Manager instance.")
        if team_id not in self._team_by_id:
            raise ValueError(f"Unknown managed club: {team_id}.")
        club = self._team_by_id[team_id]
        selection = selection or SquadSelection(club.default_lineup_ids)
        club.to_team(selection)  # Validate eligibility and goalkeeper coverage.
        tactics = tactics or TeamTactics()
        if not isinstance(tactics, TeamTactics):
            raise ValueError("Manager tactics must be a TeamTactics instance.")
        if self.manager_assignment is not None:
            raise ValueError("A season can have only one manager assignment.")
        self.manager_assignment = ManagerAssignment(manager, team_id, selection, tactics)
        return self.manager_assignment

    @property
    def results(self) -> tuple[FixtureResult, ...]:
        return tuple(self._results[fixture.id] for fixture in self.fixtures
                     if fixture.id in self._results)

    @property
    def complete(self) -> bool:
        return len(self._results) == len(self.fixtures)

    @property
    def matchdays(self) -> tuple[int, ...]:
        return tuple(sorted({fixture.matchday for fixture in self.fixtures}))

    def fixtures_for_matchday(self, matchday: int) -> tuple[Fixture, ...]:
        return tuple(fixture for fixture in self.fixtures if fixture.matchday == matchday)

    def result_for(self, fixture_id: str) -> FixtureResult | None:
        if fixture_id not in self._fixture_by_id:
            raise KeyError(f"Unknown fixture: {fixture_id}")
        return self._results.get(fixture_id)

    def play_fixture(self, fixture_id: str, *,
                     tactics: Mapping[str, TeamTactics] | None = None,
                     manager_selection: SquadSelection | None = None,
                     match_options: Mapping | None = None,
                     on_half_time: Callable[[Match], None] | None = None) -> FixtureResult:
        """Run and record one fixture; a completed result cannot be overwritten."""
        try:
            fixture = self._fixture_by_id[fixture_id]
        except KeyError as exc:
            raise KeyError(f"Unknown fixture: {fixture_id}") from exc
        if fixture_id in self._results:
            raise ValueError(f"Fixture {fixture_id} already has a recorded result.")
        if any(other.matchday < fixture.matchday and other.id not in self._results
               for other in self.fixtures):
            raise ValueError("Earlier matchdays must be complete before this fixture can start.")
        tactics_were_supplied = tactics is not None
        if tactics is None:
            tactics = {}
        if not isinstance(tactics, Mapping):
            raise ValueError("Tactics must map team IDs to TeamTactics instances.")
        unknown = set(tactics) - self._team_by_id.keys()
        if unknown:
            raise ValueError(f"Tactics supplied for unknown team IDs: {sorted(unknown)}")
        for team_id, instructions in tactics.items():
            if not isinstance(instructions, TeamTactics):
                raise ValueError(f"Tactics for {team_id} must be a TeamTactics instance.")
        if match_options is not None and not isinstance(match_options, Mapping):
            raise ValueError("Match options must be a mapping of Match arguments.")
        requested_tactics = dict(tactics)
        if self.manager_assignment is not None:
            managed_id = self.manager_assignment.team_id
            requested_tactics.setdefault(managed_id, self.manager_assignment.tactics)
        requested_options = dict(match_options or {})
        if self._run_settings is None:
            effective_tactics = requested_tactics
            options = requested_options
        else:
            effective_tactics = dict(self._run_settings["tactics"])
            options = self._run_settings["match_options"]
            manager_id = self.manager_assignment.team_id if self.manager_assignment else None
            comparable_requested = {key: value for key, value in requested_tactics.items()
                                    if key != manager_id}
            comparable_saved = {key: value for key, value in effective_tactics.items()
                                if key != manager_id}
            if tactics_were_supplied and comparable_requested != comparable_saved:
                raise ValueError("Non-manager season tactics are fixed after the first fixture; omit them to resume saved settings.")
            if self.manager_assignment is not None and self.manager_assignment.team_id in dict(tactics or {}):
                effective_tactics[self.manager_assignment.team_id] = dict(tactics)[self.manager_assignment.team_id]
            if match_options is not None and requested_options != options:
                raise ValueError("Season match settings are fixed after the first fixture; omit them to resume saved settings.")
        reserved = {"home", "away", "seed", "home_tactics", "away_tactics"} & options.keys()
        if reserved:
            raise ValueError(f"Match options cannot override fixture inputs: {sorted(reserved)}")
        home_club = self._team_by_id[fixture.home_team_id]
        away_club = self._team_by_id[fixture.away_team_id]
        if manager_selection is not None and self.manager_assignment is None:
            raise ValueError("A manager must be assigned before submitting a manager lineup.")
        if manager_selection is not None and not isinstance(manager_selection, SquadSelection):
            raise ValueError("Manager selection must be a SquadSelection instance.")
        home_selection = (self.manager_assignment.selection if self.manager_assignment
                          and self.manager_assignment.team_id == home_club.id
                          else SquadSelection(home_club.default_lineup_ids) if self.manager_assignment is None
                          else cpu_selection(home_club, fixture.seed))
        away_selection = (self.manager_assignment.selection if self.manager_assignment
                          and self.manager_assignment.team_id == away_club.id
                          else SquadSelection(away_club.default_lineup_ids) if self.manager_assignment is None
                          else cpu_selection(away_club, fixture.seed))
        if manager_selection is not None:
            if self.manager_assignment.team_id == home_club.id:
                home_selection = manager_selection
            elif self.manager_assignment.team_id == away_club.id:
                away_selection = manager_selection
        home = home_club.to_team(home_selection)
        away = away_club.to_team(away_selection)
        match = Match(home, away, seed=fixture.seed,
                      home_tactics=effective_tactics.get(home.id),
                      away_tactics=effective_tactics.get(away.id), **options)
        run_match(match, on_half_time=on_half_time)
        if match.phase != Phase.FULL_TIME:
            raise RuntimeError(f"Fixture {fixture_id} was abandoned and has no result.")
        result = FixtureResult(
            fixture_id=fixture.id,
            home_goals=match.home_goals,
            away_goals=match.away_goals,
            home_stats=match.statistics(home.id),
            away_stats=match.statistics(away.id),
            elapsed_seconds=match.elapsed_seconds,
            home_lineup=tuple(player.id for player in home.lineup),
            away_lineup=tuple(player.id for player in away.lineup),
            home_tactics=effective_tactics.get(home.id, TeamTactics()),
            away_tactics=effective_tactics.get(away.id, TeamTactics()),
        )
        self._results[fixture.id] = result
        if self._run_settings is None:
            self._run_settings = {
                "match_options": options,
                "tactics": effective_tactics,
            }
        return result

    def play_matchday(self, matchday: int, *,
                      tactics: Mapping[str, TeamTactics] | None = None,
                      manager_selection: SquadSelection | None = None,
                      match_options: Mapping | None = None,
                      on_half_time: Callable[[Match], None] | None = None) -> tuple[FixtureResult, ...]:
        """Play every not-yet-recorded fixture on a matchday, in schedule order."""
        fixtures = self.fixtures_for_matchday(matchday)
        if not fixtures:
            raise ValueError(f"Unknown matchday: {matchday}")
        if any(fixture.matchday < matchday and fixture.id not in self._results
               for fixture in self.fixtures):
            raise ValueError("Earlier matchdays must be complete before this matchday can start.")
        return tuple(self.play_fixture(fixture.id, tactics=tactics,
                                       manager_selection=manager_selection,
                                       match_options=match_options,
                                       on_half_time=on_half_time)
                     for fixture in fixtures if fixture.id not in self._results)

    def standings(self) -> tuple[Standing, ...]:
        table = {team.id: {"team": team, "played": 0, "won": 0, "drawn": 0,
                           "lost": 0, "goals_for": 0, "goals_against": 0,
                           "points": 0} for team in self.teams}
        for fixture in self.fixtures:
            result = self._results.get(fixture.id)
            if result is None:
                continue
            home, away = table[fixture.home_team_id], table[fixture.away_team_id]
            home["played"] += 1
            away["played"] += 1
            home["goals_for"] += result.home_goals
            home["goals_against"] += result.away_goals
            away["goals_for"] += result.away_goals
            away["goals_against"] += result.home_goals
            if result.home_goals > result.away_goals:
                home["won"] += 1
                away["lost"] += 1
                home["points"] += self.points_for_win
                away["points"] += self.points_for_loss
            elif result.home_goals < result.away_goals:
                away["won"] += 1
                home["lost"] += 1
                away["points"] += self.points_for_win
                home["points"] += self.points_for_loss
            else:
                home["drawn"] += 1
                away["drawn"] += 1
                home["points"] += self.points_for_draw
                away["points"] += self.points_for_draw
        standings = []
        for team_id, row in table.items():
            gd = row["goals_for"] - row["goals_against"]
            team = row.pop("team")
            standings.append(Standing(team_id=team_id, team_name=team.name,
                                      goal_difference=gd, **row))
        return tuple(sorted(standings,
                            key=lambda row: (-row.points, -row.goal_difference,
                                             -row.goals_for, row.team_id)))

    def validate(self) -> None:
        """Check schedule integrity and reconcile each stored result."""
        if type(self.season_number) is not int or self.season_number < 1:
            raise ValueError("Season number must be a positive integer.")
        if len(self.season_history) != self.season_number - 1:
            raise ValueError("Completed season history does not match current season number.")
        if any(getattr(record, "season_number", None) != index
               for index, record in enumerate(self.season_history, 1)):
            raise ValueError("Season history contains an invalid season sequence.")
        if len(self._fixture_by_id) != len(self.fixtures):
            raise ValueError("Fixture IDs must be unique.")
        if len({fixture.seed for fixture in self.fixtures}) != len(self.fixtures):
            raise ValueError("Fixture seeds must be unique within a season.")
        if self.fixtures != self._make_fixtures():
            raise ValueError("Fixtures or per-fixture seeds do not match this season's schedule seed.")
        if len(self._results) > len(self.fixtures):
            raise ValueError("Season has more results than fixtures.")
        if self._results and self._run_settings is None:
            raise ValueError("Completed fixtures must retain the settings used to simulate them.")
        if self._run_settings is not None:
            if set(self._run_settings) != {"match_options", "tactics"}:
                raise ValueError("Season run settings are malformed.")
            if set(self._run_settings["tactics"]) - self._team_by_id.keys():
                raise ValueError("Season tactics reference an unknown team.")
        if self.manager_assignment is not None:
            assignment = self.manager_assignment
            if (not isinstance(assignment.manager, Manager) or assignment.team_id not in self._team_by_id
                    or not isinstance(assignment.selection, SquadSelection)
                    or not isinstance(assignment.tactics, TeamTactics)):
                raise ValueError("Manager assignment is malformed.")
            self._team_by_id[assignment.team_id].to_team(assignment.selection)
        pair_venues: dict[tuple[str, str], dict[tuple[str, str], int]] = {}
        teams_per_day: dict[int, set[str]] = {}
        for fixture in self.fixtures:
            if fixture.home_team_id not in self._team_by_id or fixture.away_team_id not in self._team_by_id:
                raise ValueError(f"Fixture {fixture.id} references an unknown team.")
            if fixture.home_team_id == fixture.away_team_id:
                raise ValueError(f"Fixture {fixture.id} has the same home and away team.")
            if type(fixture.matchday) is not int or fixture.matchday < 1:
                raise ValueError(f"Fixture {fixture.id} has an invalid matchday.")
            if type(fixture.seed) is not int:
                raise ValueError(f"Fixture {fixture.id} has an invalid seed.")
            pair = tuple(sorted((fixture.home_team_id, fixture.away_team_id)))
            venue = (fixture.home_team_id, fixture.away_team_id)
            venues = pair_venues.setdefault(pair, {})
            venues[venue] = venues.get(venue, 0) + 1
            participants = teams_per_day.setdefault(fixture.matchday, set())
            if fixture.home_team_id in participants or fixture.away_team_id in participants:
                raise ValueError(f"A team appears more than once on matchday {fixture.matchday}.")
            participants.update((fixture.home_team_id, fixture.away_team_id))
        expected_pairs = len(self.teams) * (len(self.teams) - 1) // 2
        if (len(self.fixtures) != expected_pairs * 2 or len(pair_venues) != expected_pairs
                or any(len(venues) != 2 or any(count != 1 for count in venues.values())
                       for venues in pair_venues.values())):
            raise ValueError("Every team pair must meet twice, once at each venue.")
        for fixture_id, result in self._results.items():
            fixture = self._fixture_by_id.get(fixture_id)
            if fixture is None or result.fixture_id != fixture_id:
                raise ValueError("A result references an unknown or mismatched fixture.")
            if any(other.matchday < fixture.matchday and other.id not in self._results
                   for other in self.fixtures):
                raise ValueError("A completed fixture skips an earlier matchday.")
            if any(type(value) is not int or value < 0 for value in
                   (result.home_goals, result.away_goals, result.elapsed_seconds)):
                raise ValueError(f"Result for {fixture_id} contains a negative value.")
            if (not isinstance(result.home_stats, TeamStats)
                    or not isinstance(result.away_stats, TeamStats)
                    or result.home_stats.team_id != fixture.home_team_id
                    or result.away_stats.team_id != fixture.away_team_id
                    or result.home_stats.goals != result.home_goals
                    or result.away_stats.goals != result.away_goals):
                raise ValueError(f"Result for {fixture_id} does not reconcile with match statistics.")
            if not isinstance(result.home_tactics, TeamTactics) or not isinstance(result.away_tactics, TeamTactics):
                raise ValueError(f"Result for {fixture_id} has invalid tactical choices.")
            if result.home_lineup or result.away_lineup:
                league_players = {player.id: player for club in self.teams for player in club.players}
                for team_id, lineup in ((fixture.home_team_id, result.home_lineup),
                                        (fixture.away_team_id, result.away_lineup)):
                    if (len(lineup) != 11 or len(set(lineup)) != 11
                            or not set(lineup) <= league_players.keys()
                            or sum(league_players[pid].is_goalkeeper for pid in lineup) != 1):
                        raise ValueError(f"Result for {fixture_id} has an invalid saved lineup.")
        if self.squad_operations is not None:
            if self.squad_operations.season_number != self.season_number:
                raise ValueError("Squad operations season does not match the current season.")
            self.squad_operations.validate(self.teams)
        if self.club_finances is not None:
            if self.club_finances.current_season != self.season_number:
                raise ValueError("Finance season does not match the current season.")
            self.club_finances.validate(self.teams, fixtures=self.fixtures, results=self.results,
                                        matchdays=self.matchdays)

    @classmethod
    def _restore(cls, *, name: str, teams: tuple[Team, ...], seed: int,
                 points_for_win: int, points_for_draw: int, points_for_loss: int,
                 fixtures: tuple[Fixture, ...], results: tuple[FixtureResult, ...],
                 run_settings: dict | None, manager_assignment: ManagerAssignment | None = None,
                 squad_operations=None, club_finances=None, season_number=1,
                 season_history=()) -> "Season":
        """Rebuild validated persisted state without regenerating or losing results."""
        season = cls(name, teams, seed=seed, points_for_win=points_for_win,
                     points_for_draw=points_for_draw, points_for_loss=points_for_loss)
        if tuple(fixtures) != season.fixtures:
            raise ValueError("Saved fixtures or seeds do not match the season schedule.")
        season._results = {result.fixture_id: result for result in results}
        if len(season._results) != len(results):
            raise ValueError("Save contains duplicate fixture results.")
        season._run_settings = run_settings
        season.manager_assignment = manager_assignment
        season.season_number = season_number
        season.season_history = list(season_history)
        if squad_operations is not None:
            season.squad_operations = squad_operations
        if club_finances is not None:
            season.club_finances = club_finances
        season.validate()
        return season

    def _make_fixtures(self) -> tuple[Fixture, ...]:
        rng = Random(self.seed)
        entrants = list(self.teams)
        rng.shuffle(entrants)
        if len(entrants) % 2:
            entrants.append(None)
        first_leg: list[list[tuple[Team, Team]]] = []
        for round_index in range(len(entrants) - 1):
            pairings = []
            for pair_index in range(len(entrants) // 2):
                left, right = entrants[pair_index], entrants[-pair_index - 1]
                if left is None or right is None:
                    continue
                if (round_index + pair_index) % 2:
                    left, right = right, left
                pairings.append((left, right))
            first_leg.append(pairings)
            entrants = [entrants[0], entrants[-1], *entrants[1:-1]]
        fixtures = []
        fixture_rng = Random(self.seed ^ 0xF0955EED)
        used_seeds = set()
        for leg, rounds in enumerate((first_leg, [[(away, home) for home, away in day]
                                                    for day in first_leg])):
            for round_index, pairings in enumerate(rounds):
                matchday = leg * len(first_leg) + round_index + 1
                for pair_index, (home, away) in enumerate(pairings, start=1):
                    fixture_id = f"{self.name}:MD{matchday:02d}:{pair_index:02d}"
                    fixture_seed = fixture_rng.getrandbits(64)
                    while fixture_seed in used_seeds:
                        fixture_seed = fixture_rng.getrandbits(64)
                    used_seeds.add(fixture_seed)
                    fixtures.append(Fixture(fixture_id, matchday, home.id, away.id, fixture_seed))
        return tuple(fixtures)
