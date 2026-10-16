# Milestone 6: Offline terminal manager prototype

Milestone 6 makes the season loop usable through an interactive terminal menu.
The menu is a replaceable client over `fm95.manager.session.ManagerSession`;
future PySide6 screens can call the same manager actions.

## Launch

From the project root, with Python 3.10 or newer:

```sh
python -m fm95.manager
```

No network connection or external runtime package is required.

## Start a career

1. Select **Start new career**.
2. Enter a manager name, club count, season seed, and season name. Defaults are
   offered for club count and seed.
3. Choose a club by its number.
4. At each matchday, enter 11 squad numbers separated by commas to submit a
   lineup. The listed players are numbered in the order shown. Press Enter to
   keep the current XI. The selection must include exactly one goalkeeper;
   all other registered players become substitutes.
5. Choose a tactical preset for the fixture: balanced, pressing, possession,
   or direct. Press Enter to reuse the previous tactical settings.
6. Review the scores and basic match statistics. The table and full fixture
   list are available from the career menu.

The current example career uses generated synthetic squads. CPU-managed clubs
prepare seeded 4-3-3 lineups. Their choices are reproducible from the season's
fixture seeds.

## Save and resume

Choose **Save career** to write a local JSON save. If you do not specify a path,
the default is under `saves/`. After a career has been saved once, each completed
matchday is saved automatically to that path. From the main menu, choose **Load
career** and select a listed save or enter a path.

The existing versioned season persistence validates loaded data and preserves
fixtures, results, lineups, tactics, and manager assignment. No remote storage is
used.

## Current prototype limits

- The interface is text-only. The planned PySide6 interface is a later
  presentation layer over the same manager session and game systems.
- Club names and squad strengths come from the generated example set; there is
  no editor for custom clubs yet.
- Tactics are chosen from four presets; individual instruction sliders are not
  exposed in this prototype.
- Match results show score and key statistics rather than a live animated
  match or event-by-event commentary.
- Transfers, contracts, finances, and season progression are available as
  described in [Milestone 7](milestone7.md), [Milestone 8](milestone8.md), and
  [Milestone 9](milestone9.md).

## Validation

Run the complete suite:

```sh
python -m unittest discover -s tests -q
```

`tests/test_manager_cli.py` covers manager actions, XI and tactic recording,
save/resume, menu loading, and invalid lineup handling.
