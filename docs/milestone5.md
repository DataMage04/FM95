# Milestone 5: Offline manager season loop

Milestone 5 adds the first playable club management loop around the existing
season and match simulation. The workflow remains fully offline.

## Available features

- A season owns persistent `Club` identities and registered rosters. Each
  fixture receives a separate match `Team` containing its chosen starting XI
  and the remaining players on the bench.
- One `Manager` can be assigned to a club before the first fixture. The manager
  selects a legal starting XI and season default tactics; tactics for the
  managed club can also be changed fixture by fixture.
- The CPU prepares a legal 4-3-3 for unmanaged clubs using player role ability.
  SHA-256 tie breaks use the fixture seed and club identity, so choices replay
  consistently across runs and do not depend on Python's process hash seed.
- Fixture results record each starting XI. Saves preserve the club rosters,
  manager assignment, selected XI, tactics, schedule, results, and settings.
- Save version 2 loads version 1 season files and migrates their match-ready
  teams to persistent club rosters.

## Run and validate

From the project root:

```sh
python -m unittest discover -s tests -v
```

The Milestone 5 acceptance coverage is in `tests/test_manager_season.py`.
It checks legal selections, stable CPU selection, manager persistence,
lineup audit data, save/resume equivalence, and version 1 save migration.

The game has no network dependency. `Season`, `Club`, `Manager`,
`SquadSelection`, and `save_season`/`load_season` can be used directly by a
local application or script.

## Scope boundary

Milestone 5 does not add transfers, contracts, finances, or a graphical
interface. The offline interface and presentation layer remain planned for
Milestone 6.
