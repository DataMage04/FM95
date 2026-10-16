# FM95

FM95 is an offline football management prototype built around a seeded match
engine, synthetic player squads, and a local season system. It currently offers
an interactive terminal interface; a graphical interface is planned for later.

## Requirements

- Python 3.10 or newer
- No external runtime packages required

Run commands from the project root.

## Play a manager career

```sh
python -m fm95.manager
```

Start a career, choose a club, then use the menus to set your starting XI and
tactics before playing each matchday. Enter 11 squad numbers separated by
commas, or press Enter to keep the current lineup. Saves are local JSON files;
choose **Save career** before exiting. Once saved, completed matchdays autosave.
The load menu lists files under `saves/` and also accepts a file path. Squad
operations include contracts and transfers during pre-season and the mid-season
window; see the [Milestone 7 guide](docs/milestone7.md).

See [the CLI guide](docs/milestone6.md) for the full prototype workflow.

## Other useful commands

```sh
python main.py                              # narrated example match
python -m fm95.match.simulation --help      # batch simulation options
python -m unittest discover -s tests -q     # full automated test suite
```

## Project layout

- `fm95/match`: match engine, spatial model, mechanics, and systems
- `fm95/players` and `fm95/teams`: player, club, and squad models
- `fm95/competition`: seasons, fixtures, standings, and save/resume
- `fm95/manager`: reusable career actions and the terminal interface
- `fm95/analysis`: calibration and integrated validation tools
- `docs`: milestone notes and validation reports

Player data and attribute distributions are synthetic, and match behavior is
still being refined. See [calibration notes](docs/calibration.md) for current
scope and limitations. FM95 is designed to run locally and has no online
accounts or multiplayer.
