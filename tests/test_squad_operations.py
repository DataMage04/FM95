from pathlib import Path
import json
import tempfile
import unittest

from fm95.manager.session import ManagerSession
from fm95.manager.cli import ManagerCLI
from fm95.squad.operations import MAX_REGISTERED_PLAYERS


class SquadOperationsTests(unittest.TestCase):
    def setUp(self):
        self.session = ManagerSession.new_game(
            manager_name="Alex", club_id="club-1", clubs=4, seed=707,
            season_name="Transfer test",
        )

    def target_field_player(self):
        club, player = next((club, player) for club, player in self.session.transfer_targets()
                            if not player.is_goalkeeper)
        return club, player

    def test_transfer_updates_registration_budget_contract_and_history(self):
        seller, player = self.target_field_player()
        buyer = self.session.manager_club
        budget_before = self.session.squad_operations.budgets[buyer.id]

        record = self.session.make_transfer(player.id, fee=125_000, contract_seasons=4)

        self.assertEqual(record.player_id, player.id)
        self.assertEqual(record.from_club_id, seller.id)
        self.assertEqual(record.to_club_id, buyer.id)
        self.assertEqual(record.window, "Pre-season")
        buyer_after = self.session.manager_club
        seller_after = next(club for club in self.session.season.teams if club.id == seller.id)
        self.assertIn(player.id, {item.id for item in buyer_after.players})
        self.assertNotIn(player.id, {item.id for item in seller_after.players})
        self.assertEqual(self.session.squad_operations.contracts[player.id].end_season, 4)
        self.assertEqual(self.session.squad_operations.budgets[buyer.id], budget_before - 125_000)
        self.assertEqual(self.session.squad_operations.history, [record])

    def test_closed_window_rejects_transfer_without_mutating_state(self):
        # First of six matchdays is outside the pre-season and mid-season windows.
        self.session.play_next_matchday()
        seller, player = self.target_field_player()
        before_rosters = {club.id: tuple(p.id for p in club.players)
                          for club in self.session.season.teams}
        with self.assertRaisesRegex(ValueError, "window is closed"):
            self.session.make_transfer(player.id, fee=10)
        self.assertEqual(before_rosters, {club.id: tuple(p.id for p in club.players)
                                         for club in self.session.season.teams})
        self.assertEqual(self.session.squad_operations.history, [])

    def test_midseason_window_opens_at_the_halfway_matchday_boundary(self):
        self.session = ManagerSession.new_game(manager_name="Alex", club_id="club-1",
                                               clubs=2, seed=707, season_name="Midseason test")
        self.session.play_next_matchday()
        window, completed = self.session.squad_operations.current_window(self.session.season)
        self.assertEqual((window, completed), ("Mid-season", 1))
        _seller, player = self.target_field_player()
        record = self.session.make_transfer(player.id, fee=0)
        self.assertEqual(record.window, "Mid-season")
        with tempfile.TemporaryDirectory() as folder:
            path = self.session.save(Path(folder) / "midseason.json")
            resumed = ManagerSession.load(path)
        self.assertEqual(resumed.squad_operations.history[0].window, "Mid-season")

    def test_transfer_window_stays_closed_during_a_partially_played_matchday(self):
        fixture = self.session.season.fixtures_for_matchday(1)[0]
        self.session.season.play_fixture(fixture.id)
        self.assertEqual(self.session.squad_operations.current_window(self.session.season),
                         (None, 0))

    def test_cli_can_complete_a_market_transfer(self):
        replies = iter(["1", "25000", "2", "30000"])
        output = []
        cli = ManagerCLI(input_fn=lambda _prompt: next(replies), output_fn=output.append)
        cli.session = self.session

        cli._transfer_market()

        self.assertEqual(len(self.session.squad_operations.history), 1)
        self.assertTrue(any("Signed" in message for message in output))

    def test_budget_limit_and_contract_duration_are_checked(self):
        _seller, player = self.target_field_player()
        with self.assertRaisesRegex(ValueError, "Transfer budget"):
            self.session.make_transfer(player.id, fee=2_000_001)
        with self.assertRaisesRegex(ValueError, "between 1 and 5"):
            self.session.make_transfer(player.id, fee=0, contract_seasons=6)

    def test_roster_limit_is_enforced_while_selling_club_keeps_minimum(self):
        targets = list(self.session.transfer_targets())
        seller_targets = [item for item in targets if item[0].id == "club-2"]
        field_players = [item for item in seller_targets if not item[1].is_goalkeeper]
        reserve_keeper = next(item for item in seller_targets if item[1].is_goalkeeper)
        for seller, player in field_players[:6]:
            self.session.make_transfer(player.id, fee=0)
        seller = next(club for club in self.session.season.teams if club.id == "club-2")
        self.assertEqual(len(seller.players), 12)
        remaining = next(player for player in seller.players if not player.is_goalkeeper)
        with self.assertRaisesRegex(ValueError, "10 outfield players"):
            self.session.make_transfer(remaining.id, fee=0)
        self.session.make_transfer(reserve_keeper[1].id, fee=0)
        buyer = self.session.manager_club
        seller = next(club for club in self.session.season.teams if club.id == "club-2")
        self.assertEqual(len(buyer.players), MAX_REGISTERED_PLAYERS)
        self.assertEqual(len(seller.players), 11)
        remaining = next(player for player in seller.players if not player.is_goalkeeper)
        with self.assertRaisesRegex(ValueError, "registration limit"):
            self.session.make_transfer(remaining.id, fee=0)

    def test_transfer_state_survives_save_and_load(self):
        _seller, player = self.target_field_player()
        self.session.make_transfer(player.id, fee=88_000, contract_seasons=2)
        with tempfile.TemporaryDirectory() as folder:
            path = self.session.save(Path(folder) / "career.json")
            saved = json.loads(path.read_text(encoding="utf-8"))
            resumed = ManagerSession.load(path)

        self.assertEqual(saved["version"], 4)
        self.assertEqual(resumed.squad_operations.history, self.session.squad_operations.history)
        self.assertEqual(resumed.squad_operations.budgets, self.session.squad_operations.budgets)
        self.assertEqual(resumed.squad_operations.contracts, self.session.squad_operations.contracts)
        self.assertEqual(resumed.manager_club, self.session.manager_club)

    def test_v2_save_migrates_to_default_squad_operations(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.session.save(Path(folder) / "career.json")
            saved = json.loads(path.read_text(encoding="utf-8"))
            saved["version"] = 2
            saved.pop("squad")
            saved.pop("finances")
            path.write_text(json.dumps(saved), encoding="utf-8")
            resumed = ManagerSession.load(path)

        self.assertEqual(resumed.squad_operations.history, [])
        self.assertTrue(all(contract.end_season == 3
                            for contract in resumed.squad_operations.contracts.values()))
        self.assertTrue(all(amount > 0 for amount in resumed.squad_operations.budgets.values()))

    def test_v3_transfer_history_debits_the_migrated_cash_account(self):
        _seller, player = self.target_field_player()
        self.session.make_transfer(player.id, fee=120_000)
        with tempfile.TemporaryDirectory() as folder:
            path = self.session.save(Path(folder) / "v3.json")
            saved = json.loads(path.read_text(encoding="utf-8"))
            saved["version"] = 3
            saved.pop("finances")
            for contract in saved["squad"]["contracts"]:
                contract.pop("weekly_wage", None)
            path.write_text(json.dumps(saved), encoding="utf-8")
            resumed = ManagerSession.load(path)

        account = resumed.finances.accounts[resumed.manager_team_id]
        self.assertEqual(account.cash_balance, account.starting_balance - 120_000)
        self.assertEqual(resumed.finances.transactions[0].category, "transfer_fee")
        self.assertEqual(resumed.squad_operations.history[0].fee, 120_000)
        seller_id = resumed.squad_operations.history[0].from_club_id
        seller_account = resumed.finances.accounts[seller_id]
        self.assertEqual(seller_account.cash_balance, seller_account.starting_balance + 120_000)

    def test_contract_renewal_keeps_registration_owner(self):
        player = self.session.manager_club.players[0]
        renewed = self.session.renew_contract(player.id, seasons=5)
        self.assertEqual(renewed.club_id, self.session.manager_team_id)
        self.assertEqual(renewed.end_season, 5)


if __name__ == "__main__":
    unittest.main()
