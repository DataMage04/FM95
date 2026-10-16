"""Offline squad administration and transfer rules for one season career."""

from dataclasses import dataclass

from fm95.competition.manager import cpu_selection
from fm95.match.spatial.positions import Position
from fm95.players.model import Player
from fm95.teams.club import Club, SquadSelection


MIN_REGISTERED_PLAYERS = 11
MAX_REGISTERED_PLAYERS = 25
STARTING_TRANSFER_BUDGET = 2_000_000
DEFAULT_CONTRACT_SEASONS = 3
MAX_CONTRACT_SEASONS = 5


@dataclass(frozen=True)
class Contract:
    player_id: str
    club_id: str
    start_season: int
    end_season: int

    def __post_init__(self):
        if not isinstance(self.player_id, str) or not self.player_id.strip():
            raise ValueError("Contract needs a player ID.")
        if not isinstance(self.club_id, str) or not self.club_id.strip():
            raise ValueError("Contract needs a club ID.")
        if (type(self.start_season) is not int or type(self.end_season) is not int
                or self.start_season < 1 or self.end_season < self.start_season):
            raise ValueError("Contract seasons are invalid.")


@dataclass(frozen=True)
class TransferRecord:
    season: int
    completed_matchdays: int
    window: str
    player_id: str
    player_name: str
    from_club_id: str
    to_club_id: str
    fee: int

    def __post_init__(self):
        if type(self.season) is not int or self.season < 1:
            raise ValueError("Transfer season must be positive.")
        if type(self.completed_matchdays) is not int or self.completed_matchdays < 0:
            raise ValueError("Transfer matchday must be non-negative.")
        if self.window not in {"Pre-season", "Mid-season"}:
            raise ValueError("Transfer window is invalid.")
        for name in ("player_id", "player_name", "from_club_id", "to_club_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"Transfer {name.replace('_', ' ')} is required.")
        if self.from_club_id == self.to_club_id:
            raise ValueError("A player cannot transfer to the same club.")
        if type(self.fee) is not int or self.fee < 0:
            raise ValueError("Transfer fee must be a non-negative whole number.")


class SquadOperations:
    """Mutable career data kept separately from match and finance systems.

    Budgets are a one-time transfer allowance for this milestone. Wages, income,
    and recurring budget changes belong to the club-finances milestone.
    """

    def __init__(self, clubs, *, contracts=None, budgets=None, history=()):
        clubs = tuple(clubs)
        club_ids = {club.id for club in clubs}
        player_clubs = {player.id: club.id for club in clubs for player in club.players}
        self.contracts = dict({
            player_id: Contract(player_id, club_id, 1, DEFAULT_CONTRACT_SEASONS)
            for player_id, club_id in player_clubs.items()
        } if contracts is None else contracts)
        self.budgets = dict({club_id: STARTING_TRANSFER_BUDGET for club_id in club_ids}
                            if budgets is None else budgets)
        self.history = list(history)
        self.validate(clubs)

    def validate(self, clubs):
        clubs = tuple(clubs)
        club_by_id = {club.id: club for club in clubs}
        if len(club_by_id) != len(clubs):
            raise ValueError("Squad operations need unique club IDs.")
        players = {player.id: club.id for club in clubs for player in club.players}
        if set(self.contracts) != set(players):
            raise ValueError("Every registered player must have exactly one contract.")
        for player_id, contract in self.contracts.items():
            if (not isinstance(contract, Contract) or contract.player_id != player_id
                    or contract.club_id != players[player_id]):
                raise ValueError("A player contract does not match the registered squad.")
        if set(self.budgets) != set(club_by_id):
            raise ValueError("Transfer budgets must be set for every club.")
        if any(type(amount) is not int or amount < 0 for amount in self.budgets.values()):
            raise ValueError("Transfer budgets must be non-negative whole numbers.")
        if any(not isinstance(record, TransferRecord) for record in self.history):
            raise ValueError("Transfer history contains an invalid record.")
        if any(record.from_club_id not in club_by_id or record.to_club_id not in club_by_id
               for record in self.history):
            raise ValueError("Transfer history references an unknown club.")
        for club in clubs:
            if not MIN_REGISTERED_PLAYERS <= len(club.players) <= MAX_REGISTERED_PLAYERS:
                raise ValueError(f"{club.name} must register {MIN_REGISTERED_PLAYERS}–{MAX_REGISTERED_PLAYERS} players.")

    @staticmethod
    def current_window(season):
        """Return the available window name at the current matchday boundary."""
        completed = 0
        for matchday in season.matchdays:
            fixtures = season.fixtures_for_matchday(matchday)
            played = sum(season.result_for(fixture.id) is not None for fixture in fixtures)
            if 0 < played < len(fixtures):
                return None, completed
            if played == len(fixtures):
                completed += 1
        if completed == 0:
            return "Pre-season", completed
        midpoint = len(season.matchdays) // 2
        if completed == midpoint:
            return "Mid-season", completed
        return None, completed

    @staticmethod
    def validate_registration(club, player):
        if not isinstance(club, Club) or not isinstance(player, Player):
            raise ValueError("Registration requires a club and a Player instance.")
        if any(existing.id == player.id for existing in club.players):
            raise ValueError(f"{player.name} is already registered at {club.name}.")
        if len(club.players) >= MAX_REGISTERED_PLAYERS:
            raise ValueError(f"{club.name} has reached the {MAX_REGISTERED_PLAYERS}-player registration limit.")

    @staticmethod
    def replace_rosters(season, rosters):
        """Replace affected immutable club records and refresh legal default XIs."""
        updated = []
        for club in season.teams:
            players = tuple(rosters.get(club.id, club.players))
            if players == club.players:
                updated.append(club)
                continue
            if not MIN_REGISTERED_PLAYERS <= len(players) <= MAX_REGISTERED_PLAYERS:
                raise ValueError(f"{club.name} must keep {MIN_REGISTERED_PLAYERS}–{MAX_REGISTERED_PLAYERS} registered players.")
            if len({player.id for player in players}) != len(players):
                raise ValueError(f"{club.name} cannot register the same player twice.")
            if (not any(player.is_goalkeeper for player in players)
                    or sum(not player.is_goalkeeper for player in players) < 10):
                raise ValueError(f"{club.name} must retain a goalkeeper and at least 10 outfield players.")
            retained = tuple(pid for pid in club.default_lineup_ids
                             if any(player.id == pid for player in players))
            if len(retained) == 11 and sum(
                    next(player.is_goalkeeper for player in players if player.id == pid)
                    for pid in retained) == 1:
                lineup = retained
            else:
                keeper = next(player for player in players if player.is_goalkeeper)
                lineup = (keeper.id, *[player.id for player in players
                                      if not player.is_goalkeeper][:10])
            provisional = Club(club.id, club.name, players, lineup)
            updated.append(provisional)
        all_ids = [player.id for club in updated for player in club.players]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("A player cannot be registered at two clubs.")
        season.teams = tuple(updated)
        season._team_by_id = {club.id: club for club in season.teams}
        if season.manager_assignment is not None:
            assignment = season.manager_assignment
            managed = season._team_by_id[assignment.team_id]
            try:
                managed.to_team(assignment.selection)
            except ValueError:
                selection = SquadSelection(managed.default_lineup_ids)
                from fm95.competition.manager import ManagerAssignment
                season.manager_assignment = ManagerAssignment(
                    assignment.manager, assignment.team_id, selection, assignment.tactics
                )

    def complete_transfer(self, season, player_id, *, fee, contract_seasons=DEFAULT_CONTRACT_SEASONS):
        """Move a player between clubs after validating window, roster, and budget."""
        window, completed = self.current_window(season)
        if window is None:
            raise ValueError("The transfer window is closed. Transfers are allowed pre-season and mid-season.")
        if type(fee) is not int or fee < 0:
            raise ValueError("Transfer fee must be a non-negative whole number.")
        if type(contract_seasons) is not int or not 1 <= contract_seasons <= MAX_CONTRACT_SEASONS:
            raise ValueError(f"A new contract must be between 1 and {MAX_CONTRACT_SEASONS} seasons.")
        player = next((player for club in season.teams for player in club.players
                       if player.id == player_id), None)
        if player is None:
            raise ValueError(f"Unknown registered player: {player_id}.")
        buyer_id = season.manager_assignment.team_id if season.manager_assignment else None
        seller_id = self.contracts[player_id].club_id
        if buyer_id is None:
            raise ValueError("A manager must be assigned before making transfers.")
        if seller_id == buyer_id:
            raise ValueError("That player is already registered at your club.")
        buyer = season._team_by_id[buyer_id]
        seller = season._team_by_id[seller_id]
        if len(buyer.players) >= MAX_REGISTERED_PLAYERS:
            raise ValueError(f"{buyer.name} has reached the {MAX_REGISTERED_PLAYERS}-player registration limit.")
        if len(seller.players) <= MIN_REGISTERED_PLAYERS:
            raise ValueError(f"{seller.name} must keep at least {MIN_REGISTERED_PLAYERS} players registered.")
        if player.is_goalkeeper and sum(p.is_goalkeeper for p in seller.players) <= 1:
            raise ValueError(f"{seller.name} must keep at least one goalkeeper.")
        if not player.is_goalkeeper and sum(not p.is_goalkeeper for p in seller.players) <= 10:
            raise ValueError(f"{seller.name} must keep at least 10 outfield players for a legal XI.")
        if fee > self.budgets[buyer_id]:
            raise ValueError(f"Transfer budget is {self.budgets[buyer_id]:,}; fee is {fee:,}.")

        rosters = {
            seller_id: tuple(p for p in seller.players if p.id != player_id),
            buyer_id: (*buyer.players, player),
        }
        self.replace_rosters(season, rosters)
        self.contracts.pop(player_id)
        self.contracts[player_id] = Contract(player_id, buyer_id, 1, contract_seasons)
        self.budgets[buyer_id] -= fee
        self.history.append(TransferRecord(1, completed, window, player.id, player.name,
                                           seller_id, buyer_id, fee))
        self.validate(season.teams)
        return self.history[-1]

    def renew_contract(self, season, player_id, *, seasons):
        if type(seasons) is not int or not 1 <= seasons <= MAX_CONTRACT_SEASONS:
            raise ValueError(f"A contract must be between 1 and {MAX_CONTRACT_SEASONS} seasons.")
        contract = self.contracts.get(player_id)
        if contract is None or contract.club_id not in {club.id for club in season.teams}:
            raise ValueError(f"Unknown registered player: {player_id}.")
        self.contracts[player_id] = Contract(player_id, contract.club_id, 1, seasons)
        self.validate(season.teams)
        return self.contracts[player_id]
