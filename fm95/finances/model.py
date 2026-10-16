"""Deterministic cash flow for offline season careers."""

from dataclasses import dataclass, replace


DEFAULT_CASH_BALANCE = 10_000_000
DEFAULT_SPONSORSHIP_PER_MATCHDAY = 160_000
DEFAULT_STADIUM_CAPACITY = 20_000
DEFAULT_TICKET_PRICE = 25
DEFAULT_STADIUM_COST = 45_000
FINANCE_CATEGORIES = {"wages", "sponsorship", "ticket_income", "stadium_cost", "transfer_fee"}


@dataclass(frozen=True)
class ClubAccount:
    club_id: str
    starting_balance: int = DEFAULT_CASH_BALANCE
    cash_balance: int = DEFAULT_CASH_BALANCE
    sponsorship_per_matchday: int = DEFAULT_SPONSORSHIP_PER_MATCHDAY
    stadium_capacity: int = DEFAULT_STADIUM_CAPACITY
    ticket_price: int = DEFAULT_TICKET_PRICE
    stadium_cost_per_home_match: int = DEFAULT_STADIUM_COST

    def __post_init__(self):
        if not isinstance(self.club_id, str) or not self.club_id.strip():
            raise ValueError("Finance account needs a club ID.")
        for name in ("starting_balance", "sponsorship_per_matchday", "stadium_capacity",
                     "ticket_price", "stadium_cost_per_home_match"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name.replace('_', ' ').capitalize()} must be a non-negative whole number.")
        if type(self.cash_balance) is not int:
            raise ValueError("Cash balance must be a whole number.")


@dataclass(frozen=True)
class FinanceTransaction:
    matchday: int
    club_id: str
    category: str
    description: str
    amount: int
    season_number: int = 1

    def __post_init__(self):
        if type(self.matchday) is not int or self.matchday < 0:
            raise ValueError("Transaction matchday must be non-negative.")
        if not isinstance(self.club_id, str) or not self.club_id.strip():
            raise ValueError("Transaction needs a club ID.")
        if self.category not in FINANCE_CATEGORIES:
            raise ValueError("Transaction category is invalid.")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Transaction needs a description.")
        if type(self.amount) is not int:
            raise ValueError("Transaction amount must be a whole number.")
        if type(self.season_number) is not int or self.season_number < 1:
            raise ValueError("Transaction season number must be positive.")


class ClubFinances:
    """Cash accounts, deterministic matchday flows, and an audit ledger."""

    def __init__(self, clubs, *, accounts=None, transactions=(), processed_matchdays=(),
                 processed_season_matchdays=None, current_season=1):
        clubs = tuple(clubs)
        club_ids = {club.id for club in clubs}
        self.accounts = dict({
            club_id: ClubAccount(club_id)
            for club_id in club_ids
        } if accounts is None else accounts)
        self.transactions = list(transactions)
        if type(current_season) is not int or current_season < 1:
            raise ValueError("Current finance season must be positive.")
        self.current_season = current_season
        self.processed_season_matchdays = set(
            (current_season, day) for day in processed_matchdays
        ) if processed_season_matchdays is None else set(processed_season_matchdays)
        self.validate(clubs)

    @property
    def processed_matchdays(self):
        """Current season's processed days, retained for the Milestone 8 API."""
        return {day for season_number, day in self.processed_season_matchdays
                if season_number == self.current_season}

    def validate(self, clubs, *, fixtures=None, results=None, matchdays=None):
        clubs = tuple(clubs)
        club_ids = {club.id for club in clubs}
        if set(self.accounts) != club_ids:
            raise ValueError("Finance accounts must exist for every club.")
        if any(not isinstance(account, ClubAccount) or account.club_id != club_id
               for club_id, account in self.accounts.items()):
            raise ValueError("Finance account keys do not match their club IDs.")
        if any(not isinstance(item, FinanceTransaction) or item.club_id not in club_ids
               for item in self.transactions):
            raise ValueError("Finance ledger contains an invalid or unknown club transaction.")
        if matchdays is not None and any(item.season_number == self.current_season
                                         and item.matchday not in {*matchdays, 0}
                                         for item in self.transactions):
            raise ValueError("Finance transaction references an unknown matchday.")
        for item in self.transactions:
            if ((item.category in {"wages", "stadium_cost"} and item.amount > 0)
                    or (item.category in {"sponsorship", "ticket_income"} and item.amount < 0)):
                raise ValueError("Finance transaction amount has the wrong sign for its category.")
        if any(not isinstance(item, tuple) or len(item) != 2
               or any(type(value) is not int or value < 1 for value in item)
               for item in self.processed_season_matchdays):
            raise ValueError("Processed finance season/matchday entries are invalid.")
        if matchdays is not None and self.processed_matchdays - set(matchdays):
            raise ValueError("Finance ledger references an unknown matchday.")
        for club_id, account in self.accounts.items():
            ledger_total = sum(entry.amount for entry in self.transactions if entry.club_id == club_id)
            if account.cash_balance != account.starting_balance + ledger_total:
                raise ValueError(f"Cash balance for {club_id} does not reconcile with the finance ledger.")
        # Every settled historical day must have one wages and sponsorship
        # entry per club. Home entries are checked against the active schedule.
        for season_number, day in self.processed_season_matchdays:
            day_entries = [entry for entry in self.transactions
                           if entry.season_number == season_number and entry.matchday == day]
            for club_id in club_ids:
                categories = [entry.category for entry in day_entries if entry.club_id == club_id]
                if categories.count("wages") != 1 or categories.count("sponsorship") != 1:
                    raise ValueError(f"Matchday {day} does not have one wage and sponsorship entry for {club_id}.")
                if categories.count("ticket_income") != categories.count("stadium_cost") or categories.count("ticket_income") > 1:
                    raise ValueError(f"Matchday {day} has inconsistent home-match finance entries for {club_id}.")
        if fixtures is not None and results is not None:
            result_ids = {result.fixture_id for result in results}
            for day in self.processed_matchdays:
                if any(fixture.matchday == day and fixture.id not in result_ids for fixture in fixtures):
                    raise ValueError(f"Finances were processed before matchday {day} was complete.")
                day_entries = [entry for entry in self.transactions
                               if entry.season_number == self.current_season and entry.matchday == day]
                homes = {fixture.home_team_id for fixture in fixtures if fixture.matchday == day}
                for club_id in club_ids:
                    categories = [entry.category for entry in day_entries if entry.club_id == club_id]
                    if categories.count("wages") != 1 or categories.count("sponsorship") != 1:
                        raise ValueError(f"Matchday {day} does not have one wage and sponsorship entry for {club_id}.")
                    expected_home_entries = 1 if club_id in homes else 0
                    if (categories.count("ticket_income") != expected_home_entries
                            or categories.count("stadium_cost") != expected_home_entries):
                        raise ValueError(f"Matchday {day} has inconsistent home-match finance entries for {club_id}.")

    def can_pay(self, club_id, amount):
        if type(amount) is not int or amount < 0:
            return False
        account = self.accounts.get(club_id)
        return account is not None and account.cash_balance >= amount

    def record_transfer_fee(self, club_id, fee, *, matchday, season_number=1):
        if type(fee) is not int or fee < 0:
            raise ValueError("Transfer fee must be a non-negative whole number.")
        if not self.can_pay(club_id, fee):
            balance = self.accounts[club_id].cash_balance
            raise ValueError(f"Club cash is {balance:,}; transfer fee is {fee:,}.")
        if fee:
            self._post(FinanceTransaction(matchday, club_id, "transfer_fee",
                                          "Player transfer fee", -fee, season_number))

    def receive_transfer_fee(self, club_id, fee, *, matchday, season_number=1):
        if type(fee) is not int or fee < 0:
            raise ValueError("Transfer fee must be a non-negative whole number.")
        if fee:
            self._post(FinanceTransaction(matchday, club_id, "transfer_fee",
                                          "Player transfer fee received", fee, season_number))

    def migrate_legacy_transfers(self, history):
        """Carry Milestone 7 transfer spending into the new cash accounts."""
        for record in history:
            if record.fee:
                self.record_transfer_fee(record.to_club_id, record.fee,
                                         matchday=record.completed_matchdays)
                self.receive_transfer_fee(record.from_club_id, record.fee,
                                          matchday=record.completed_matchdays)

    def process_matchday(self, season, squad_operations, matchday):
        """Settle one complete matchday once; repeats are safe after loading a save."""
        if matchday not in season.matchdays:
            raise ValueError(f"Unknown matchday: {matchday}.")
        if any(season.result_for(fixture.id) is None
               for fixture in season.fixtures_for_matchday(matchday)):
            raise ValueError("Matchday finances settle only after every fixture is complete.")
        season_number = season.season_number
        key = (season_number, matchday)
        if key in self.processed_season_matchdays:
            return ()

        standings = season.standings()
        ranks = {row.team_id: index for index, row in enumerate(standings)}
        club_count = max(1, len(season.teams) - 1)
        day_fixtures = season.fixtures_for_matchday(matchday)
        home_fixture = {fixture.home_team_id: fixture for fixture in day_fixtures}
        entries = []
        for club in season.teams:
            account = self.accounts[club.id]
            wages = sum(squad_operations.contracts[player.id].weekly_wage
                        for player in club.players)
            entries.append(FinanceTransaction(matchday, club.id, "wages",
                f"Squad wages for matchday {matchday}", -wages, season_number))
            entries.append(FinanceTransaction(matchday, club.id, "sponsorship",
                f"Sponsorship for matchday {matchday}", account.sponsorship_per_matchday, season_number))
            fixture = home_fixture.get(club.id)
            if fixture is not None:
                rank = ranks[club.id]
                fill_rate = .45 + .20 * (len(standings) - 1 - rank) / club_count
                attendance = int(account.stadium_capacity * fill_rate)
                ticket_income = attendance * account.ticket_price
                entries.append(FinanceTransaction(matchday, club.id, "ticket_income",
                    f"Home attendance: {attendance:,}", ticket_income, season_number))
                entries.append(FinanceTransaction(matchday, club.id, "stadium_cost",
                    f"Stadium operations for matchday {matchday}",
                    -account.stadium_cost_per_home_match, season_number))

        for entry in entries:
            self._post(entry)
        self.current_season = season_number
        self.processed_season_matchdays.add(key)
        self.validate(season.teams, fixtures=season.fixtures, results=season.results,
                      matchdays=season.matchdays)
        return tuple(entries)

    def _post(self, transaction):
        account = self.accounts[transaction.club_id]
        self.accounts[transaction.club_id] = replace(
            account, cash_balance=account.cash_balance + transaction.amount
        )
        self.transactions.append(transaction)

    def account_summary(self, club_id, squad_operations):
        account = self.accounts[club_id]
        wages = sum(contract.weekly_wage for contract in squad_operations.contracts.values()
                    if contract.club_id == club_id)
        income = sum(item.amount for item in self.transactions
                     if item.club_id == club_id and item.amount > 0)
        expenses = -sum(item.amount for item in self.transactions
                        if item.club_id == club_id and item.amount < 0)
        return {
            "account": account,
            "weekly_wages": wages,
            "transfer_budget": squad_operations.budgets[club_id],
            "income_to_date": income,
            "expenses_to_date": expenses,
        }
