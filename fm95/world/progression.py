"""Deterministic player and league progression between seasons."""

from dataclasses import dataclass, replace
from hashlib import sha256
from random import Random

from fm95.players.attributes import Attributes
from fm95.players.factory import generate_attributes, generate_decisions
from fm95.players.model import Player
from fm95.squad.operations import (
    Contract, MAX_REGISTERED_PLAYERS, STARTING_TRANSFER_BUDGET,
)
from fm95.teams.club import Club, SquadSelection


@dataclass(frozen=True)
class SeasonRecord:
    season_number: int
    season_name: str
    champion_id: str
    champion_name: str
    table: tuple[tuple[str, int, int, int, int], ...]
    retired_players: tuple[str, ...] = ()
    released_players: tuple[str, ...] = ()
    generated_players: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.season_number) is not int or self.season_number < 1:
            raise ValueError("Season record number must be positive.")
        if not all(isinstance(value, str) and value.strip() for value in
                   (self.season_name, self.champion_id, self.champion_name)):
            raise ValueError("Season record needs a name and champion.")
        object.__setattr__(self, "table", tuple(tuple(row) for row in self.table))
        if not self.table or any(len(row) != 5 or not isinstance(row[0], str)
                                 or any(type(value) is not int for value in row[1:])
                                 for row in self.table):
            raise ValueError("Season record table is invalid.")
        if self.champion_id not in {row[0] for row in self.table}:
            raise ValueError("Season champion must appear in the final table.")
        for name in ("retired_players", "released_players", "generated_players"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
            if any(not isinstance(value, str) or not value.strip()
                   for value in getattr(self, name)):
                raise ValueError(f"Season record {name} contains an invalid player label.")


def advance_season(season) -> SeasonRecord:
    """Record a completed year, age/develop players, then build the next year.

    Club identities and league membership stay fixed. Retirements and expired
    contracts create squad vacancies that are filled by deterministic youth.
    """
    if not season.complete:
        raise ValueError("The season can advance only after every fixture is complete.")
    if season.season_number < 1:
        raise ValueError("Season number is invalid.")

    current_number = season.season_number
    next_number = current_number + 1
    table_rows = season.standings()
    champion = table_rows[0]
    record = SeasonRecord(
        season_number=current_number,
        season_name=season.name,
        champion_id=champion.team_id,
        champion_name=champion.team_name,
        table=tuple((row.team_id, row.points, row.goal_difference,
                     row.goals_for, row.played) for row in table_rows),
    )

    retired, released, generated = [], [], []
    rosters = {}
    new_players = {}
    for club in season.teams:
        retained = []
        vacancies = []
        for player in club.players:
            contract = season.squad_operations.contracts[player.id]
            aged = _develop_player(player, season.seed, current_number)
            rng = _player_rng(season.seed, current_number, player.id, "exit")
            if aged.age >= 40 or rng.random() < _retirement_chance(aged.age):
                retired.append(f"{player.name} ({club.name})")
                vacancies.append(player.position)
            elif contract.end_season <= current_number:
                released.append(f"{player.name} ({club.name})")
                vacancies.append(player.position)
            else:
                retained.append(aged)
        youth_intake = list(vacancies)
        if len(retained) + len(youth_intake) < min(MAX_REGISTERED_PLAYERS, len(club.players) + 1):
            youth_intake.append(_intake_position(club, next_number))
        for index, position in enumerate(youth_intake, 1):
            youth = _generate_youth(club, position, seed=season.seed,
                                    season_number=next_number, index=index,
                                    squad=retained)
            retained.append(youth)
            new_players[youth.id] = Contract(
                youth.id, club.id, next_number, next_number + 2,
                max(5_000, int(round((8_000 + 12_000 * youth.potential) / 100) * 100)),
            )
            generated.append(f"{youth.name} ({club.name})")
        lineup = tuple(pid for pid in club.default_lineup_ids
                       if any(player.id == pid for player in retained))
        if len(lineup) != 11 or sum(p.is_goalkeeper for p in retained
                                    if p.id in lineup) != 1:
            keeper = next(player for player in retained if player.is_goalkeeper)
            lineup = (keeper.id, *[p.id for p in retained if not p.is_goalkeeper][:10])
        rosters[club.id] = Club(club.id, club.name, tuple(retained), lineup)

    # Refresh immutable club records, preserving a legal XI for the manager.
    season.teams = tuple(rosters[club.id] for club in season.teams)
    season._team_by_id = {club.id: club for club in season.teams}
    if season.manager_assignment is not None:
        assignment = season.manager_assignment
        managed = season._team_by_id[assignment.team_id]
        try:
            managed.to_team(assignment.selection)
        except ValueError:
            season.manager_assignment = replace(
                assignment, selection=SquadSelection(managed.default_lineup_ids))

    old_contracts = season.squad_operations.contracts
    contracts = {
        player.id: (new_players[player.id] if player.id in new_players else old_contracts[player.id])
        for club in season.teams for player in club.players
    }
    season.squad_operations.contracts = contracts
    season.squad_operations.season_number = next_number
    season.squad_operations.budgets = {
        club.id: STARTING_TRANSFER_BUDGET for club in season.teams
    }
    season.squad_operations.validate(season.teams)

    season.season_number = next_number
    season.season_history.append(replace(
        record,
        retired_players=tuple(retired), released_players=tuple(released),
        generated_players=tuple(generated),
    ))
    season.seed = _next_season_seed(season.seed, current_number)
    season.name = f"{_base_season_name(season.name)} (Season {next_number})"
    season.fixtures = season._make_fixtures()
    season._fixture_by_id = {fixture.id: fixture for fixture in season.fixtures}
    season._results = {}
    season._run_settings = None
    season.club_finances.current_season = next_number
    season.validate()
    return season.season_history[-1]


def _develop_player(player: Player, career_seed: int, season_number: int) -> Player:
    next_age = player.age + 1
    rng = _player_rng(career_seed, season_number, player.id, "development")
    values = {}
    for name in Attributes.__dataclass_fields__:
        current = getattr(player.attributes, name)
        if name == "injury_proneness":
            delta = max(0, next_age - 31) * .0015 + rng.uniform(-.004, .004)
        elif next_age <= 23:
            mean = _ability_mean(player.attributes)
            headroom = max(0.0, player.potential - mean)
            delta = min(.025, headroom * .10) * rng.uniform(.55, 1.35)
        elif next_age <= 29:
            delta = rng.uniform(-.006, .006)
        else:
            delta = -min(.025, .002 + (next_age - 30) * .002) * rng.uniform(.65, 1.25)
        values[name] = max(0.0, min(1.0, current + delta))
    return replace(player, age=next_age, attributes=Attributes(**values))


def _generate_youth(club, position, *, seed, season_number, index, squad):
    key = f"{seed}|{season_number}|{club.id}|{index}|youth".encode()
    rng = Random(int.from_bytes(sha256(key).digest()[:8], "big"))
    player_id = f"{club.id}-y{season_number:03d}-{index:02d}"
    name = f"{club.name} Youth {season_number}-{index:02d}"
    average = sum(_ability_mean(player.attributes) for player in squad) / max(1, len(squad))
    strength = max(.25, min(.75, average - .04))
    attributes = generate_attributes(seed=seed + season_number * 7919 + index,
                                     player_id=player_id, position=position,
                                     team_strength=strength)
    potential = max(.45, min(.98, _ability_mean(attributes) + rng.uniform(.08, .24)))
    return Player(
        id=player_id, name=name, is_goalkeeper=position.value == "GK",
        position=position, attributes=attributes,
        decisions=generate_decisions(seed=seed + season_number * 7919 + index,
                                     player_id=player_id, position=position),
        age=rng.randint(16, 19), potential=potential,
    )


def _ability_mean(attributes):
    fields = [name for name in Attributes.__dataclass_fields__ if name != "injury_proneness"]
    return sum(getattr(attributes, name) for name in fields) / len(fields)


def _intake_position(club, season_number):
    roles = ("CM", "CB", "ST", "RW", "LB", "GK", "DM", "AM", "LW", "RB")
    from fm95.match.spatial.positions import Position
    return Position(roles[(season_number - 2) % len(roles)])


def _retirement_chance(age):
    return {34: .01, 35: .04, 36: .09, 37: .18, 38: .36, 39: .65}.get(age, 0.0)


def _player_rng(seed, season_number, player_id, purpose):
    data = f"{seed}|{season_number}|{player_id}|{purpose}".encode()
    return Random(int.from_bytes(sha256(data).digest()[:8], "big"))


def _next_season_seed(seed, season_number):
    data = f"FM95|{seed}|{season_number}|next-season".encode()
    return int.from_bytes(sha256(data).digest()[:8], "big")


def _base_season_name(name):
    marker = " (Season "
    return name.rsplit(marker, 1)[0] if marker in name else name
