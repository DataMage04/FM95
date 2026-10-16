# Milestone 4: persistent season saves

Milestone 4 adds restartable competition saves. A save can be made between
fixtures, loaded in a new Python process, and continued from the next unplayed
fixture. Match-in-progress state is deliberately not saved.

## Stored state

- Season name and seed, plus the points awarded for wins, draws, and losses.
- Club IDs and names; each player's identity, position, goalkeeper role,
  execution attributes, decision tendencies, starting lineup, and bench.
- The complete home-and-away schedule, including matchday, home/away assignments,
  fixture IDs, and each fixture's independent random seed.
- Completed scores, elapsed match time, and full team-statistics snapshots.
- The match configuration and team tactics selected for the first completed
  fixture. Those settings are then fixed for the season, retained in the save,
  and reused for remaining fixtures after load.

Standings are recalculated from recorded results when a season is loaded. The
save format has an explicit version. Loading checks the version, reconstructed
schedule and seeds, roster references, result-to-fixture links, score/statistic
agreement, and configuration values. Saving writes a temporary file beside the
target, flushes it, then replaces the target atomically.

## Python API

```python
from fm95.competition.persistence import load_season, save_season
from fm95.competition.season import Season
from fm95.match.mechanics.actions import ActionConfig
from fm95.players.demo import demo_team

teams = [demo_team(f"club-{n}", f"Club {n}", include_bench=True)
         for n in range(4)]
season = Season("2026/27", teams, seed=95)
season.play_matchday(
    season.matchdays[0],
    match_options={"action_config": ActionConfig(interval_seconds=90)},
)
save_season(season, "saves/2026-27.json")

# Later, including from another process:
season = load_season("saves/2026-27.json")
for matchday in season.matchdays:
    season.play_matchday(matchday)  # already completed fixtures are skipped
save_season(season, "saves/2026-27.json")
```

Once the first fixture has completed, its match options and tactics become
season settings; omit them on later calls to reuse them. Mid-match callbacks are
runtime Python functions and are not included in save files. Save only after a
fixture has finished.

## Validation

Run the save/restart/resume acceptance check:

```sh
python -m fm95.competition.persistence_validation --clubs 4 --seed 95 --json
```

It compares a completed season with one saved after the first matchday, loaded,
and resumed. The acceptance report is [milestone4-validation.json](milestone4-validation.json).

The save schema is version 1. Incompatible versions are rejected rather than
silently interpreted. A future schema change must increment the version and
provide an explicit migration before old saves can be loaded.
