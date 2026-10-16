from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from fm95.match.mechanics.actions import ActionConfig
from fm95.manager.session import ManagerSession
from fm95.players.model import Player
from fm95.squad.operations import Contract
from fm95.competition.persistence import load_season


FAST_MATCH = {"action_config": ActionConfig(interval_seconds=5400)}


def finish_season(session):
    while session.next_matchday is not None:
        session.play_next_matchday(match_options=FAST_MATCH)


class WorldProgressionTests(unittest.TestCase):
    def make_session(self, seed=171):
        return ManagerSession.new_game(manager_name="Alex", club_id="club-1", clubs=2,
                                       seed=seed, season_name="World test")

    def test_cannot_advance_before_all_fixtures_are_complete(self):
        session = self.make_session()
        with self.assertRaisesRegex(ValueError, "every fixture"):
            session.advance_season()

    def test_rollover_keeps_league_fixed_and_ages_develops_and_generates_players(self):
        session = self.make_session()
        club_ids = tuple(club.id for club in session.season.teams)
        player = session.manager_club.players[0]
        old_age = player.age
        old_attributes = player.attributes
        finish_season(session)

        record = session.advance_season()

        self.assertEqual(record.season_number, 1)
        self.assertIn(record.champion_id, club_ids)
        self.assertEqual(tuple(club.id for club in session.season.teams), club_ids)
        self.assertEqual(session.season.season_number, 2)
        self.assertEqual(session.season.season_history, [record])
        aged = next(p for club in session.season.teams for p in club.players
                    if p.id == player.id)
        self.assertEqual(aged.age, old_age + 1)
        self.assertNotEqual(aged.attributes, old_attributes)
        self.assertTrue(record.generated_players)
        self.assertTrue(all(len(club.players) >= 11 for club in session.season.teams))
        self.assertTrue(all(contract.end_season >= 2
                            for contract in session.squad_operations.contracts.values()))
        self.assertEqual(session.squad_operations.budgets,
                         {club.id: 2_000_000 for club in session.season.teams})

    def test_retirement_and_expiring_contracts_are_replaced_legally(self):
        session = self.make_session()
        target_club = session.season.teams[0]
        retired = target_club.players[0]
        released = target_club.players[1]
        updated_players = tuple(
            replace(player, age=39) if player.id == retired.id else player
            for player in target_club.players
        )
        updated_club = replace(target_club, players=updated_players)
        session.season.teams = tuple(updated_club if club.id == target_club.id else club
                                     for club in session.season.teams)
        session.season._team_by_id = {club.id: club for club in session.season.teams}
        session.squad_operations.contracts[released.id] = Contract(
            released.id, target_club.id, 1, 1,
            session.squad_operations.contracts[released.id].weekly_wage)
        finish_season(session)

        record = session.advance_season()

        self.assertTrue(any(retired.name in item for item in record.retired_players))
        self.assertTrue(any(released.name in item for item in record.released_players))
        club = next(club for club in session.season.teams if club.id == target_club.id)
        self.assertNotIn(retired.id, {p.id for p in club.players})
        self.assertNotIn(released.id, {p.id for p in club.players})
        self.assertEqual(len(club.players), len(target_club.players) + 1)
        self.assertEqual(len(session.squad_operations.contracts),
                         sum(len(item.players) for item in session.season.teams))

    def test_season_finances_and_progression_survive_save_resume(self):
        session = self.make_session(818)
        finish_season(session)
        session.advance_season()
        target = next(player for _club, player in session.transfer_targets()
                      if not player.is_goalkeeper)
        transfer = session.make_transfer(target.id, fee=50_000, contract_seasons=3)
        contract = session.squad_operations.contracts[target.id]
        self.assertEqual(transfer.season, 2)
        self.assertEqual((contract.start_season, contract.end_season), (2, 4))
        session.play_next_matchday(match_options=FAST_MATCH)
        with tempfile.TemporaryDirectory() as folder:
            path = session.save(Path(folder) / "multi-season.json")
            resumed = ManagerSession.load(path)

        self.assertEqual(resumed.season.season_number, 2)
        self.assertEqual(resumed.season.season_history, session.season.season_history)
        self.assertEqual(resumed.season.teams, session.season.teams)
        self.assertEqual(resumed.finances.transactions, session.finances.transactions)
        self.assertEqual(resumed.finances.processed_matchdays, {1})
        self.assertEqual(resumed.finances.current_season, 2)
        self.assertTrue(any(item.season_number == 2 and item.category == "transfer_fee"
                            for item in resumed.finances.transactions))
        self.assertEqual(resumed.next_matchday, session.next_matchday)

    def test_multi_season_progression_is_seed_reproducible(self):
        sessions = (self.make_session(192), self.make_session(192))
        records = []
        for session in sessions:
            finish_season(session)
            records.append(session.advance_season())
        self.assertEqual(records[0], records[1])
        self.assertEqual(sessions[0].season.teams, sessions[1].season.teams)
        self.assertEqual(sessions[0].season.fixtures, sessions[1].season.fixtures)

    def test_milestone8_save_migrates_with_default_player_ages(self):
        session = self.make_session()
        session.play_next_matchday()
        with tempfile.TemporaryDirectory() as folder:
            path = session.save(Path(folder) / "m8.json")
            data = json.loads(path.read_text(encoding="utf-8"))
            data["version"] = 4
            data.pop("progression")
            finances = data["finances"]
            finances["processed_matchdays"] = [
                day for _season, day in finances.pop("processed_season_matchdays")
            ]
            finances.pop("current_season")
            for transaction in finances["transactions"]:
                transaction.pop("season_number")
            for club in data["teams"]:
                for player in club["players"]:
                    player.pop("age")
                    player.pop("potential")
            path.write_text(json.dumps(data), encoding="utf-8")
            resumed = ManagerSession.load(path)

        self.assertEqual(resumed.season.season_number, 1)
        self.assertTrue(all(player.age == 25 and player.potential == .7
                            for club in resumed.season.teams for player in club.players))
        self.assertEqual(resumed.finances.processed_matchdays, {1})


if __name__ == "__main__":
    unittest.main()
