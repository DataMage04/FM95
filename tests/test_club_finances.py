from pathlib import Path
import tempfile
import unittest

from fm95.finances.model import ClubAccount
from fm95.manager.session import ManagerSession


class ClubFinanceTests(unittest.TestCase):
    def setUp(self):
        self.session = ManagerSession.new_game(
            manager_name="Alex", club_id="club-1", clubs=2, seed=818,
            season_name="Finance test",
        )

    def test_completed_matchday_posts_wages_sponsorship_ticket_income_and_stadium_costs(self):
        self.session.play_next_matchday()
        finances = self.session.finances
        self.assertEqual(finances.processed_matchdays, {1})
        categories = {item.category for item in finances.transactions}
        self.assertEqual(categories, {"wages", "sponsorship", "ticket_income", "stadium_cost"})
        for club in self.session.season.teams:
            summary = finances.account_summary(club.id, self.session.squad_operations)
            self.assertGreater(summary["weekly_wages"], 0)
            self.assertEqual(summary["account"].cash_balance,
                             summary["account"].starting_balance +
                             sum(item.amount for item in finances.transactions if item.club_id == club.id))

    def test_matchday_settlement_is_idempotent(self):
        self.session.play_next_matchday()
        before = tuple(self.session.finances.transactions)
        self.assertEqual(self.session.finances.process_matchday(
            self.session.season, self.session.squad_operations, 1), ())
        self.assertEqual(tuple(self.session.finances.transactions), before)

    def test_unfinished_matchday_does_not_settle_finances(self):
        session = ManagerSession.new_game(manager_name="Alex", club_id="club-1",
                                          clubs=4, seed=818)
        fixture = session.season.fixtures_for_matchday(1)[0]
        session.season.play_fixture(fixture.id)
        with self.assertRaisesRegex(ValueError, "every fixture is complete"):
            session.finances.process_matchday(session.season, session.squad_operations, 1)
        self.assertEqual(session.finances.transactions, [])

    def test_matchday_finances_persist_and_resume(self):
        self.session.play_next_matchday()
        with tempfile.TemporaryDirectory() as folder:
            path = self.session.save(Path(folder) / "career.json")
            resumed = ManagerSession.load(path)
        self.assertEqual(resumed.finances.processed_matchdays, {1})
        self.assertEqual(resumed.finances.transactions, self.session.finances.transactions)
        self.assertEqual(resumed.finances.accounts, self.session.finances.accounts)

    def test_financial_transactions_can_drive_balance_below_zero(self):
        club_id = self.session.season.teams[1].id
        self.session.finances.accounts[club_id] = ClubAccount(
            club_id=club_id, starting_balance=1, cash_balance=1,
            sponsorship_per_matchday=0, stadium_capacity=0,
            ticket_price=0, stadium_cost_per_home_match=0,
        )
        self.session.play_next_matchday()
        self.assertLess(self.session.finances.accounts[club_id].cash_balance, 0)

    def test_transfer_fee_cannot_exceed_cash_even_when_transfer_allowance_is_sufficient(self):
        buyer_id = self.session.manager_team_id
        self.session.finances.accounts[buyer_id] = ClubAccount(
            club_id=buyer_id, starting_balance=0, cash_balance=0
        )
        target = next(player for _club, player in self.session.transfer_targets())
        before = {club.id: tuple(player.id for player in club.players)
                  for club in self.session.season.teams}
        with self.assertRaisesRegex(ValueError, "Club cash"):
            self.session.make_transfer(target.id, fee=100)
        self.assertEqual(before, {club.id: tuple(player.id for player in club.players)
                                  for club in self.session.season.teams})

    def test_transfer_fee_moves_cash_from_buyer_to_seller_and_wage_is_charged(self):
        seller, player = next((club, player) for club, player in self.session.transfer_targets()
                              if not player.is_goalkeeper)
        buyer_id = self.session.manager_team_id
        buyer_before = self.session.finances.accounts[buyer_id].cash_balance
        seller_before = self.session.finances.accounts[seller.id].cash_balance

        self.session.make_transfer(player.id, fee=100_000, weekly_wage=90_000)

        self.assertEqual(self.session.finances.accounts[buyer_id].cash_balance, buyer_before - 100_000)
        self.assertEqual(self.session.finances.accounts[seller.id].cash_balance, seller_before + 100_000)
        self.assertEqual(self.session.squad_operations.contracts[player.id].weekly_wage, 90_000)
        self.session.play_next_matchday()
        buyer_wages = next(item.amount for item in self.session.finances.transactions
                           if item.category == "wages" and item.club_id == buyer_id)
        self.assertEqual(buyer_wages, -sum(contract.weekly_wage
                         for contract in self.session.squad_operations.contracts.values()
                         if contract.club_id == buyer_id))

    def test_finance_screen_shows_cash_and_wage_information(self):
        from fm95.manager.cli import ManagerCLI

        output = []
        cli = ManagerCLI(output_fn=output.append)
        cli.session = self.session
        cli._show_finances()
        self.assertTrue(any("Cash balance" in line for line in output))
        self.assertTrue(any("Registered squad wages" in line for line in output))


if __name__ == "__main__":
    unittest.main()
