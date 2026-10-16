from pathlib import Path
import tempfile
import unittest

from fm95.manager.cli import ManagerCLI
from fm95.manager.session import ManagerSession
from fm95.match.tactics import preset
from fm95.teams.club import SquadSelection


class ManagerSessionTests(unittest.TestCase):
    def test_play_save_and_resume_preserve_matchday_manager_choices(self):
        session = ManagerSession.new_game(manager_name="Alex", club_id="club-1",
                                          clubs=2, seed=812, season_name="CLI test")
        club = session.manager_club
        selected = list(session.current_selection.starting_xi)
        selected[-1] = club.bench[1].id
        selection = SquadSelection(tuple(selected))
        tactic = preset("pressing")

        results = session.play_next_matchday(selection=selection, tactics=tactic)

        self.assertEqual(len(results), 1)
        fixture = next(item for item in session.season.fixtures if item.id == results[0].fixture_id)
        actual_lineup = (results[0].home_lineup if fixture.home_team_id == club.id
                         else results[0].away_lineup)
        actual_tactics = (results[0].home_tactics if fixture.home_team_id == club.id
                          else results[0].away_tactics)
        self.assertEqual(actual_lineup, selection.starting_xi)
        self.assertEqual(actual_tactics, tactic)
        self.assertEqual(session.next_matchday, 2)

        with tempfile.TemporaryDirectory() as folder:
            save_path = session.save(Path(folder) / "career.json")
            resumed = ManagerSession.load(save_path)
            self.assertEqual(resumed.current_selection, selection)
            self.assertEqual(resumed.current_tactics, tactic)
            self.assertEqual(resumed.next_matchday, 2)
            resumed.play_next_matchday()
            self.assertTrue(resumed.season.complete)


class ManagerCLITests(unittest.TestCase):
    def test_new_career_opens_manager_hub(self):
        replies = iter(["1", "Alex", "", "", "", "1", "3", "6", "4"])
        output = []
        cli = ManagerCLI(input_fn=lambda _prompt: next(replies), output_fn=output.append)

        cli.run()

        self.assertTrue(any("Career started" in message for message in output))
        self.assertTrue(any("League table" in message for message in output))
        self.assertEqual(cli.session.manager_club.id, "club-1")

    def test_squad_prompt_rejects_illegal_xi_then_accepts_default(self):
        session = ManagerSession.new_game(manager_name="Alex", club_id="club-1", clubs=2)
        replies = iter(["1,1,1,1,1,1,1,1,1,1,1", ""])
        output = []
        cli = ManagerCLI(input_fn=lambda _prompt: next(replies), output_fn=output.append)
        cli.session = session

        selected = cli._choose_lineup()

        self.assertEqual(selected, session.current_selection)
        self.assertTrue(any(message.startswith("Invalid lineup:") for message in output))

    def test_main_menu_loads_saved_game_and_returns_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            save_dir = Path(folder) / "saves"
            session = ManagerSession.new_game(manager_name="Alex", club_id="club-1",
                                              clubs=2, seed=55, season_name="Saved Career")
            session.save(save_dir / "career.json")
            replies = iter(["2", "1", "3", "6", "4"])
            output = []
            cli = ManagerCLI(input_fn=lambda _prompt: next(replies),
                             output_fn=output.append, save_dir=save_dir)
            cli.run()

        self.assertTrue(any("Loaded Saved Career" in message for message in output))
        self.assertTrue(any("League table" in message for message in output))
        self.assertEqual(cli.session.manager_club.id, "club-1")


if __name__ == "__main__":
    unittest.main()
