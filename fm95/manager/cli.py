"""Interactive, offline prototype for managing an FM95 season."""

from pathlib import Path
import sys

from fm95.manager.session import ManagerSession, DEFAULT_CLUB_NAMES, TACTIC_PRESETS
from fm95.match.tactics import preset
from fm95.teams.club import SquadSelection


class ManagerCLI:
    """Text menu that delegates game actions to ``ManagerSession``."""

    def __init__(self, *, input_fn=input, output_fn=print, save_dir: str | Path = "saves"):
        self.input = input_fn
        self.output = output_fn
        self.save_dir = Path(save_dir)
        self.session: ManagerSession | None = None

    def run(self) -> None:
        while True:
            self.output("\nFM95 — Offline Manager Prototype")
            if self.session is not None:
                self.output("1. Continue current career")
                self.output("2. Start new career")
                self.output("3. Load career")
                self.output("4. Quit")
                choice = self._ask_choice("Choose: ", {"1", "2", "3", "4"})
                if choice == "1":
                    self._career_menu()
                elif choice == "2":
                    self._new_career()
                elif choice == "3":
                    self._load_career()
                else:
                    return
            else:
                self.output("1. Start new career")
                self.output("2. Load career")
                self.output("3. Quit")
                choice = self._ask_choice("Choose: ", {"1", "2", "3"})
                if choice == "1":
                    self._new_career()
                elif choice == "2":
                    self._load_career()
                else:
                    return

    def _new_career(self) -> None:
        self.output("\nNew career")
        manager_name = self.input("Manager name [Manager]: ").strip() or "Manager"
        clubs = self._ask_integer("Number of clubs [4]: ", default=4, minimum=2, maximum=20)
        seed = self._ask_integer("Season seed [95]: ", default=95)
        season_name = self.input(f"Season name [FM95 Season {seed}]: ").strip() or f"FM95 Season {seed}"
        self.output("\nChoose your club:")
        for index in range(clubs):
            name = DEFAULT_CLUB_NAMES[index] if index < len(DEFAULT_CLUB_NAMES) else f"Local Club {index + 1}"
            self.output(f"{index + 1}. {name}")
        club_choice = self._ask_integer("Club number: ", minimum=1, maximum=clubs)
        club_id = f"club-{club_choice}"
        try:
            self.session = ManagerSession.new_game(
                manager_name=manager_name, club_id=club_id, clubs=clubs,
                seed=seed, season_name=season_name,
            )
            self.output(f"Career started: {season_name}; you manage {self.session.manager_club.name}.")
            self._career_menu()
        except (TypeError, ValueError) as exc:
            self.output(f"Could not start career: {exc}")

    def _load_career(self) -> None:
        self.output("\nLoad career")
        files = sorted(self.save_dir.glob("*.json")) if self.save_dir.exists() else []
        for index, path in enumerate(files, 1):
            self.output(f"{index}. {path.name}")
        prompt = "Choose a save number, or enter a file path"
        if files:
            prompt += " (Enter cancels)"
        prompt += ": "
        choice = self.input(prompt).strip()
        if not choice:
            return
        if choice.isdigit() and 1 <= int(choice) <= len(files):
            path = files[int(choice) - 1]
        else:
            path = Path(choice).expanduser()
        try:
            self.session = ManagerSession.load(path)
            self.output(f"Loaded {self.session.season.name}; manager: "
                        f"{self.session.season.manager_assignment.manager.name}; "
                        f"club: {self.session.manager_club.name}.")
            self._career_menu()
        except (OSError, TypeError, ValueError) as exc:
            self.output(f"Could not load career: {exc}")

    def _career_menu(self) -> None:
        assert self.session is not None
        while True:
            next_day = self.session.next_matchday
            status = (f"Matchday {next_day}/{len(self.session.season.matchdays)}"
                      if next_day is not None else "Season complete")
            self.output(f"\n{self.session.season.name} — {self.session.manager_club.name} — {status}")
            self.output("1. Play next matchday")
            self.output("2. View squad")
            self.output("3. View league table")
            self.output("4. View fixtures and results")
            self.output("5. Save career")
            self.output("6. Return to main menu")
            self.output("7. Transfer market")
            self.output("8. View contracts / renew a contract")
            self.output("9. Transfer history")
            choice = self._ask_choice("Choose: ", {"1", "2", "3", "4", "5", "6", "7", "8", "9"})
            if choice == "1":
                self._play_next_matchday()
            elif choice == "2":
                self._show_squad()
            elif choice == "3":
                self._show_table()
            elif choice == "4":
                self._show_fixtures()
            elif choice == "5":
                self._save_career()
            elif choice == "7":
                self._transfer_market()
            elif choice == "8":
                self._show_contracts()
            elif choice == "9":
                self._show_transfer_history()
            else:
                return

    def _play_next_matchday(self) -> None:
        assert self.session is not None
        matchday = self.session.next_matchday
        if matchday is None:
            self.output("This season has no remaining fixtures.")
            return
        fixture = next((item for item in self.session.season.fixtures_for_matchday(matchday)
                        if self.session.season.result_for(item.id) is None
                        and self.session.manager_team_id in (item.home_team_id, item.away_team_id)), None)
        selection = self._choose_lineup() if fixture is not None else self.session.current_selection
        tactics = self._choose_tactics() if fixture is not None else self.session.current_tactics
        self.output(f"Simulating matchday {matchday}...")
        try:
            results = self.session.play_next_matchday(selection=selection, tactics=tactics)
        except (TypeError, ValueError, RuntimeError) as exc:
            self.output(f"Matchday could not be completed: {exc}")
            return
        for result in results:
            self._show_match_result(result)
        if self.session.save_path is not None:
            self.session.save()
            self.output(f"Autosaved: {self.session.save_path}")

    def _choose_lineup(self) -> SquadSelection:
        assert self.session is not None
        club = self.session.manager_club
        current = self.session.current_selection
        self.output("\nYour registered squad:")
        for index, player in enumerate(club.players, 1):
            marker = " *" if player.id in current.starting_xi else ""
            self.output(f"{index:2}. {player.name:<24} {player.position.value}{marker}")
        self.output("Enter 11 squad numbers separated by commas, or press Enter to keep this XI.")
        while True:
            raw = self.input("Starting XI: ").strip()
            if not raw:
                return current
            try:
                indexes = [int(value.strip()) for value in raw.split(",")]
                if any(index < 1 or index > len(club.players) for index in indexes):
                    raise ValueError(f"Choose numbers from 1 to {len(club.players)}.")
                selection = SquadSelection(tuple(club.players[index - 1].id for index in indexes))
                club.to_team(selection)
                return selection
            except (TypeError, ValueError) as exc:
                self.output(f"Invalid lineup: {exc}")

    def _choose_tactics(self):
        assert self.session is not None
        self.output("\nChoose tactics for this fixture:")
        for index, name in enumerate(TACTIC_PRESETS, 1):
            self.output(f"{index}. {name.title()}")
        self.output("Press Enter to keep the previous tactical settings.")
        while True:
            raw = self.input("Tactics: ").strip()
            if not raw:
                return self.session.current_tactics
            if raw.isdigit() and 1 <= int(raw) <= len(TACTIC_PRESETS):
                return preset(TACTIC_PRESETS[int(raw) - 1])
            self.output(f"Enter a number from 1 to {len(TACTIC_PRESETS)}, or press Enter.")

    def _show_squad(self) -> None:
        assert self.session is not None
        club = self.session.manager_club
        selected = set(self.session.current_selection.starting_xi)
        self.output(f"\n{club.name} — squad ({len(club.players)} players)")
        for player in club.players:
            status = "Starting XI" if player.id in selected else "Substitute"
            self.output(f"{player.name:<25} {player.position.value:<3} {status}")
        self.output("You can change the XI when preparing your next fixture.")

    def _transfer_market(self) -> None:
        assert self.session is not None
        operations = self.session.squad_operations
        window, completed = operations.current_window(self.session.season)
        club = self.session.manager_club
        budget = operations.budgets[club.id]
        self.output(f"\nTransfer market — {window or 'window closed'}; "
                    f"{completed} matchdays complete; transfer budget {budget:,}")
        if window is None:
            self.output("Transfers are available before matchday 1 and at the mid-season break.")
            return
        targets = self.session.transfer_targets()
        if not targets:
            self.output("No players are available from other clubs.")
            return
        self.output(" #  Player                     Pos  Club")
        for index, (selling_club, player) in enumerate(targets, 1):
            self.output(f"{index:>2}. {player.name:<25} {player.position.value:<4} {selling_club.name}")
        raw = self.input("Player number to sign, or Enter to return: ").strip()
        if not raw:
            return
        try:
            index = int(raw)
            if not 1 <= index <= len(targets):
                raise ValueError(f"Choose a number from 1 to {len(targets)}.")
            player = targets[index - 1][1]
            fee = self._ask_integer("Transfer fee [0]: ", default=0, minimum=0)
            duration = self._ask_integer("Contract length in seasons [3]: ", default=3,
                                         minimum=1, maximum=5)
            record = self.session.make_transfer(player.id, fee=fee, contract_seasons=duration)
            self.output(f"Signed {record.player_name} from {targets[index - 1][0].name} "
                        f"for {record.fee:,}; contract through season {duration}.")
            self._autosave_squad_change()
        except (TypeError, ValueError) as exc:
            self.output(f"Transfer not completed: {exc}")

    def _show_contracts(self) -> None:
        assert self.session is not None
        club = self.session.manager_club
        operations = self.session.squad_operations
        self.output(f"\nContracts — {club.name}")
        for index, player in enumerate(club.players, 1):
            contract = operations.contracts[player.id]
            self.output(f"{index:2}. {player.name:<25} through season {contract.end_season}")
        raw = self.input("Player number to renew, or Enter to return: ").strip()
        if not raw:
            return
        try:
            index = int(raw)
            if not 1 <= index <= len(club.players):
                raise ValueError(f"Choose a number from 1 to {len(club.players)}.")
            player = club.players[index - 1]
            seasons = self._ask_integer("New contract length in seasons [3]: ", default=3,
                                        minimum=1, maximum=5)
            contract = self.session.renew_contract(player.id, seasons=seasons)
            self.output(f"{player.name} is contracted through season {contract.end_season}.")
            self._autosave_squad_change()
        except (TypeError, ValueError) as exc:
            self.output(f"Contract not updated: {exc}")

    def _show_transfer_history(self) -> None:
        assert self.session is not None
        history = self.session.squad_operations.history
        self.output("\nTransfer history")
        if not history:
            self.output("No transfers have been completed.")
            return
        clubs = {club.id: club.name for club in self.session.season.teams}
        for record in history:
            self.output(f"Season {record.season}, {record.window}: {record.player_name} — "
                        f"{clubs[record.from_club_id]} → {clubs[record.to_club_id]} "
                        f"({record.fee:,})")

    def _autosave_squad_change(self) -> None:
        assert self.session is not None
        if self.session.save_path is not None:
            self.session.save()
            self.output(f"Autosaved: {self.session.save_path}")

    def _show_table(self) -> None:
        assert self.session is not None
        self.output("\nLeague table")
        self.output("\n Pos  Club                       P   W   D   L   GD  Pts")
        for position, row in enumerate(self.session.season.standings(), 1):
            self.output(f"{position:>3}  {row.team_name:<24} {row.played:>2} {row.won:>3} "
                        f"{row.drawn:>3} {row.lost:>3} {row.goal_difference:>4} {row.points:>4}")

    def _show_fixtures(self) -> None:
        assert self.session is not None
        clubs = {club.id: club.name for club in self.session.season.teams}
        self.output("\nFixtures and results")
        for matchday in self.session.season.matchdays:
            self.output(f"Matchday {matchday}")
            for fixture in self.session.season.fixtures_for_matchday(matchday):
                result = self.session.season.result_for(fixture.id)
                score = (f"{result.home_goals}–{result.away_goals}" if result is not None else "vs")
                self.output(f"  {clubs[fixture.home_team_id]} {score} {clubs[fixture.away_team_id]}")

    def _show_match_result(self, result) -> None:
        assert self.session is not None
        fixture = next(item for item in self.session.season.fixtures if item.id == result.fixture_id)
        clubs = {club.id: club.name for club in self.session.season.teams}
        self.output(f"\n{clubs[fixture.home_team_id]} {result.home_goals}–{result.away_goals} "
                    f"{clubs[fixture.away_team_id]}")
        for name, stats in ((clubs[fixture.home_team_id], result.home_stats),
                            (clubs[fixture.away_team_id], result.away_stats)):
            self.output(f"  {name}: shots {stats.shots} ({stats.shots_on_target} on target), "
                        f"possession {stats.possession_percentage:.1f}%, xG {stats.expected_goals:.2f}")

    def _save_career(self) -> None:
        assert self.session is not None
        current = str(self.session.save_path) if self.session.save_path else ""
        default = current or str(self.save_dir / f"{self.session.season.name.replace(' ', '_')}.json")
        raw = self.input(f"Save path [{default}]: ").strip()
        try:
            path = self.session.save(raw or default)
            self.output(f"Saved career to {path}")
        except (OSError, TypeError, ValueError) as exc:
            self.output(f"Could not save career: {exc}")

    def _ask_choice(self, prompt: str, valid: set[str]) -> str:
        while True:
            choice = self.input(prompt).strip()
            if choice in valid:
                return choice
            self.output("Please choose one of the listed options.")

    def _ask_integer(self, prompt: str, *, default: int | None = None,
                     minimum: int | None = None, maximum: int | None = None) -> int:
        while True:
            raw = self.input(prompt).strip()
            if not raw and default is not None:
                return default
            try:
                value = int(raw)
                if minimum is not None and value < minimum:
                    raise ValueError
                if maximum is not None and value > maximum:
                    raise ValueError
                return value
            except ValueError:
                limits = (f" from {minimum}" if minimum is not None else "")
                limits += (f" to {maximum}" if maximum is not None else "")
                self.output(f"Enter a whole number{limits}.")


def main() -> None:
    cli = ManagerCLI()
    try:
        cli.run()
    except (EOFError, KeyboardInterrupt):
        print("\nFM95 closed. Save before exiting next time to keep your progress.")


if __name__ == "__main__":
    main()
