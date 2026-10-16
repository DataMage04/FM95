"""Reusable manager actions shared by the CLI and future graphical clients."""

from pathlib import Path
import re

from fm95.competition.manager import Manager
from fm95.competition.persistence import load_season, save_season
from fm95.competition.season import FixtureResult, Season
from fm95.match.tactics import TeamTactics
from fm95.players.factory import generate_team
from fm95.teams.club import SquadSelection


DEFAULT_CLUB_NAMES = (
    "Windhoek FC", "Coastal United", "Highland Rovers", "Desert Athletic",
)
DEFAULT_STRENGTHS = (.58, .54, .50, .46)
TACTIC_PRESETS = ("balanced", "pressing", "possession", "direct")


class ManagerSession:
    """Small application-facing interface over the season domain model."""

    def __init__(self, season: Season, *, save_path: str | Path | None = None):
        if not isinstance(season, Season) or season.manager_assignment is None:
            raise ValueError("A manager session requires a season with an assigned manager.")
        self.season = season
        self.save_path = Path(save_path) if save_path is not None else None

    @classmethod
    def new_game(cls, *, manager_name: str, club_id: str, clubs: int = 4,
                 seed: int = 95, season_name: str = "FM95 Season") -> "ManagerSession":
        if type(clubs) is not int or not 2 <= clubs <= 20:
            raise ValueError("A prototype season needs between 2 and 20 clubs.")
        if type(seed) is not int:
            raise ValueError("Season seed must be an integer.")
        teams = []
        for index in range(clubs):
            name = (DEFAULT_CLUB_NAMES[index] if index < len(DEFAULT_CLUB_NAMES)
                    else f"Local Club {index + 1}")
            strength = DEFAULT_STRENGTHS[index] if index < len(DEFAULT_STRENGTHS) else .5
            teams.append(generate_team(f"club-{index + 1}", name,
                                       seed=seed + index * 1009,
                                       team_strength=strength))
        season = Season(season_name, teams, seed=seed)
        season.assign_manager(Manager("local-manager", manager_name), club_id)
        return cls(season)

    @classmethod
    def load(cls, path: str | Path) -> "ManagerSession":
        source = Path(path)
        season = load_season(source)
        if season.manager_assignment is None:
            raise ValueError("This save has no manager career to resume.")
        return cls(season, save_path=source)

    @property
    def manager_team_id(self) -> str:
        return self.season.manager_assignment.team_id

    @property
    def manager_club(self):
        return next(club for club in self.season.teams if club.id == self.manager_team_id)

    @property
    def next_matchday(self) -> int | None:
        for matchday in self.season.matchdays:
            if any(self.season.result_for(fixture.id) is None
                   for fixture in self.season.fixtures_for_matchday(matchday)):
                return matchday
        return None

    @property
    def current_selection(self) -> SquadSelection:
        for fixture in reversed(self.season.fixtures):
            result = self.season.result_for(fixture.id)
            if result is None or self.manager_team_id not in (fixture.home_team_id, fixture.away_team_id):
                continue
            lineup = result.home_lineup if fixture.home_team_id == self.manager_team_id else result.away_lineup
            if lineup:
                return SquadSelection(lineup)
        return self.season.manager_assignment.selection

    @property
    def current_tactics(self) -> TeamTactics:
        for fixture in reversed(self.season.fixtures):
            result = self.season.result_for(fixture.id)
            if result is None or self.manager_team_id not in (fixture.home_team_id, fixture.away_team_id):
                continue
            return (result.home_tactics if fixture.home_team_id == self.manager_team_id
                    else result.away_tactics)
        return self.season.manager_assignment.tactics

    def play_next_matchday(self, *, selection: SquadSelection | None = None,
                           tactics: TeamTactics | None = None) -> tuple[FixtureResult, ...]:
        matchday = self.next_matchday
        if matchday is None:
            return ()
        selection = selection or self.current_selection
        tactics = tactics or self.current_tactics
        if selection is not None:
            self.manager_club.to_team(selection)
        if tactics is not None and not isinstance(tactics, TeamTactics):
            raise ValueError("Tactics must be a TeamTactics instance.")
        tactic_map = ({self.manager_team_id: tactics} if tactics is not None else None)
        results = self.season.play_matchday(matchday, manager_selection=selection,
                                            tactics=tactic_map)
        return results

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path is not None else self.save_path
        if target is None:
            slug = re.sub(r"[^A-Za-z0-9_-]+", "_", self.season.name).strip("_") or "career"
            target = Path("saves") / f"{slug}.json"
        self.save_path = save_season(self.season, target)
        return self.save_path
