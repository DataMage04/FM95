# Milestone 3: in-memory competitions and seasons

Milestone 3 adds a round-robin season loop on top of the match engine. A season
takes match-ready `Team` instances, a name and a base seed. It creates a seeded
home-and-away fixture list, runs fixtures through the same `Match` implementation,
stores full-time scores and match statistics, and calculates a table.

```python
from fm95.demo import demo_team
from fm95.season import Season

clubs = [demo_team("north", "North"), demo_team("south", "South")]
season = Season("2026/27", clubs, seed=95)

for matchday in season.matchdays:
    season.play_matchday(matchday)

for place, row in enumerate(season.standings(), start=1):
    print(place, row.team_name, row.points, row.goal_difference)
```

The default scoring is three points for a win and one for a draw. Table order is
points, goal difference, goals scored, then team ID for a stable final ordering.
Each fixture records its own 64-bit seed; its simulation can therefore be
reproduced without replaying earlier matchdays. `play_matchday` accepts per-team
`TeamTactics` and shared `Match` configuration options. It requires previous
matchdays to be complete and skips fixtures already recorded, which supports
resuming a partially played matchday. An abandoned engine match is left without a
league result. A completed fixture cannot be overwritten.

`Season.validate()` checks the full home-and-away pairing, that a team appears at
most once per matchday, and that recorded scores agree with each match's goal
statistics. `season.complete` reports whether every scheduled fixture has a
result. Season data lives only in memory; there is no save/load format or database
integration in this milestone.

This layer reuses the engine's seeded pseudo-random behavior. Identical squads,
fixture seed, match configuration and code produce the same match output. That is
useful for reproducible testing and replay; it does not claim to reproduce the
same variability model or realism as Football Manager.

Automated coverage lives in `tests/test_season.py` and checks even and odd league
schedules, deterministic fixture seeds, match execution and replay, matchday
progression, duplicate-result protection, and result/table reconciliation.
For a full-season acceptance run, execute `python -m fm95.season_validation
--clubs 4 --seed 95 --json`. The checked-in
[`milestone3-validation.json`](milestone3-validation.json) records the four-club
run. This checks end-to-end consistency and deterministic execution, not match
realism or calibration.
