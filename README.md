# FM95

A Python football manager built from the match engine outward. **Milestone 1 is
still in progress:** the engine now runs reproducible spatial match prototypes,
but its football behavior and attribute effects are not yet calibrated.

Python 3.10 or newer; no external runtime dependencies.

## Run and verify

```sh
python main.py
python -m unittest discover -s tests -v
python -m fm95.batch --matches 2 --seed 95 --json
```

The demo uses synthetic equal-ability teams, different tactical instructions,
automatic substitutions, and opt-in injury generation. It prints sample actions,
shots, restarts, substitutions, and statistics. The current regression suite has
**233 tests**.

A batch defaults to balanced tactics with automatic management and random injuries
disabled. Enable those features explicitly:

```sh
python -m fm95.batch --matches 2 --injuries --auto-substitutions --json
python -m fm95.batch --matches 2 --home-style pressing --away-style direct --json
```

The example styles are `balanced`, `pressing`, `possession`, and `direct`. They are
provisional configurations for exploring behavior, not validated tactical advice.
Use `python -m fm95.batch --help` for isolation switches.

## Implemented foundations

| Area | Current behavior |
| --- | --- |
| Lifecycle | One-second clock, first half, explicit halftime pause/resume, reversed ends, full time, abandonment |
| Players and squads | Immutable player identities, assigned positions, 11-player starting lineups, named benches, active-player views |
| Spatial state | Metric pitch geometry, precise normalized ball/player locations, formation targets, coarse 3-by-3 context zones |
| Possession | Controlled, loose/aerial, and pending-restart states; recovery contests and possession accounting |
| Passing | Completed, intercepted, loose, out-of-play, and offside deliveries; forward runs, through balls, and tactical long passes |
| Defending | Closing down, basic marking, pressure, pressing challenges, tackles, dispossessions, fouls, and shot blocks |
| Shooting | Goals, held saves, misses, parries, rebounds, and headed shots; recorded scoring probabilities and model xG |
| Crossing | Open-play/corner deliveries, aerial contests, headers, headed clearances, keeper claims and punches |
| Restarts | Kickoffs, throw-ins, corners, goal kicks, short/direct free kicks, penalties, indirect free kicks, and injury dropped balls |
| Offside | Position snapshots at the teammate's touch, checked at represented receptions, recoveries, and aerial challenges |
| Discipline | Yellow cards, second yellows, straight reds, active-player exclusion, emergency keepers, minimum-player handling |
| Substitutions | Single/grouped changes at stoppages and halftime, configurable limits/opportunities, no return substitutions |
| Condition | Stamina-dependent depletion, represented movement costs, stoppage/halftime recovery, effective abilities and movement limits |
| Management | Read-only fatigue recommendations and optional automatic fatigue/injury replacements |
| Injuries | Optional open-play/foul incidents, match-ending withdrawals, replacement recommendations, short-handed play |
| Team tactics | Independent tempo, pressing, defensive line, width, passing directness, and attacking preferences; live changes |
| Diagnostics | Timestamped events, immutable statistics/condition snapshots, seeded batches, JSON configuration and result summaries |

## Match state and timing

`Match.start()` begins play. `step()` advances one simulated second; `resume()`
starts the second half after the halftime pause. `run_match(match)` performs this
loop automatically and supports an optional `on_half_time` management callback.

Home attacks right in the first half and left in the second. Locations use fixed
normalized coordinates: x runs left to right and y bottom to top. `Pitch` converts
them to metres. Zones are derived from those coordinates; they do not rotate with
the teams.

`match.possession`, `match.loose_ball`, and `match.pending_restart` expose the
current ownership/restart state. `match.ball_location` includes dead-ball spots.
`player_locations(team_id)` gives actual represented locations;
`formation_reference_locations(team_id)` gives instruction-adjusted targets.
Changing instructions moves targets, not existing players instantaneously.

The default action interval is six seconds. Tempo changes the possessing team's
open-play interval. Loose balls, kickoffs and pending restarts retain the base
interval; movement reach and injury exposure use actual elapsed action time.
Whistles end periods at 2700 and 5400 seconds. A pending penalty resolves before
the whistle at that timestamp; general added time is not implemented.

For completed matches, controlled seconds + loose-ball seconds + dead-ball
seconds equal 5400. Possession percentages use controlled time only. Legacy
isolation modes can retain earlier instant/held restart conventions.

## Attributes, condition and actions

`Attributes` is immutable and currently uses a temporary normalized 0–1 scale,
with .5 neutral. Its fields are passing, finishing, shot-stopping, dribbling,
tackling, crossing, heading, handling, penalties, free kicks, stamina, and injury
proneness. There is **no permanent overall rating**.

Actions use the involved player's effective abilities. Fatigue changes those
effective abilities without mutating base attributes. Stamina affects depletion;
injury proneness affects the provisional injury-risk model. Neither is reduced
as a performance skill by fatigue.

`condition(team_id, player_id)` returns an immutable `PlayerCondition` containing
energy, seconds played, and represented running distance. Unused substitutes stay
fresh; withdrawn/dismissed/substituted players stop accumulating workload. Running
totals exclude abstract pass relocations, kickoff resets, and administrative
set-piece placement. They are not full player-tracking measurements.

Normal passing and open-play shooting combine coarse zone context, live pressure,
and individual abilities. Direct free kicks additionally use metric distance and
angle. Crossing/heading/handling affect their respective interactions. Probabilities
are bounded and preserve forced 0/1 settings used for deterministic scenarios.

## Team instructions

`TeamTactics` is immutable. All fields range from 0 (low) through .5 (balanced) to
1 (high): `tempo`, `pressing`, `defensive_line`, `width`, `passing_directness`,
`crossing`, `dribbling`, `shooting`, and `through_balls`.

```python
from fm95.demo import demo_team
from fm95.match import Match
from fm95.tactics import TeamTactics

match = Match(
    demo_team("home", "Home", include_bench=True),
    demo_team("away", "Away", include_bench=True),
    seed=95,
    home_tactics=TeamTactics(tempo=.7, pressing=.8, defensive_line=.7),
)
match.start()
match.set_tactics("away", TeamTactics(width=.8, passing_directness=.8))
```

Pressing changes challenge frequency and defending workload, not tackling ability
or instantaneous running speed. High tempo increases possession workload and
action frequency; physical movement still uses elapsed time. Line height adjusts
back-line/defensive-midfield targets; width spreads or narrows outfield targets.
Attacking preferences change choices rather than finishing/passing skill.
Direct passing can skip a zone, with additional forward-distance completion risk.
Live changes emit `tactics_changed` events.

## Substitutions and injuries

`Team.bench` stores named substitutes; `Team.lineup` retains the original starting
team. All squad IDs must be unique within and across the two teams.

```python
# At an eligible stoppage, including the initial kickoff setup:
match.substitute("home", "home-9", "home-18")
# Several changes may share one opportunity:
match.substitute_many("away", (("away-7", "away-15"), ("away-9", "away-18")))
```

Incoming outfield players inherit tactical slots. Validation is atomic. Sent-off
players cannot be replaced, and substituted players cannot return. Defaults allow
five replacements across three in-play opportunities; halftime changes use player
allowance but no opportunity. Repeated requests at one stoppage share an opportunity.
`SubstitutionConfig` makes these limits configurable. Keeper replacements and
restoration of an emergency keeper's outfield role are supported.

`AutoSubstitutionConfig(enabled=True)` enables automatic management; it is off by
default. `substitution_recommendations(team_id)` remains read-only in manual mode.
The fatigue policy considers condition, expected halftime recovery, suitable cover,
role-specific effective abilities, and remaining limits. It protects the current
restart taker and avoids replacing recent substitutes solely for fatigue.

`InjuryConfig(enabled=True)` enables provisional random open-play and foul injuries.
All represented injuries force withdrawal for the remainder of this match.
`injure_player(team_id, player_id)` also supports deterministic scenarios even when
random generation is disabled. `injury(team_id, player_id)` retains incident history.
Existing foul/boundary restarts take precedence; other injury stoppages award a
short dropped-ball restart, with the defending keeper receiving drops in their area.

Automatic managers prioritise injury replacements over fatigue changes, without
waiting for fatigue thresholds or minimum playing time. Manual managers can replace
withdrawn players at the stoppage. If limits/bench options prevent a change, teams
can continue short-handed with an emergency keeper if needed. Fewer than seven
available players prevents continued play; a manager may restore seven through a
legal injury replacement before the next step.

## Events, statistics and batch output

Events retain action participants, locations, relevant effective attributes,
adjusted probabilities, outcomes, and reasons. Offside snapshots preserve position
at the teammate's touch. Substitution events record outgoing/incoming IDs, condition,
and whether the change was automatic.

`statistics(team_id)` returns a fresh immutable snapshot. It includes passing,
shooting, model xG, challenges, fouls/cards, restarts, crosses/headers, keeper
interventions, offsides, condition/workload, substitutions/injuries and tactical changes.
Useful reconciliation checks include:

- Failed pass attempts = opposition interceptions + misplaced passes + passes out
  + passes flagged offside. A later offside after a loose-ball recovery does not
  count the same pass twice.
- Shots on target = goals + opposition saves, including parries.
- Model xG = the sum of recorded unconditional shot-scoring probabilities,
  including blocked/saved/missed attempts.

Model xG describes this engine's assumptions; it is not an empirical expected-goals
model. Batch match i uses seed + i, retains aggregates rather than full event logs,
and reports completed/abandoned matches separately. JSON includes both teams'
instructions, feature configurations, scoreline frequencies, and mean statistics.
The same seed reproduces results for the same inputs, engine version and runtime;
changing instructions or features can change all subsequent random draws.

## Remaining Milestone 1 work

Next: **live formation changes and individual player roles/instructions**.
Further completion and review work includes richer coordinated attacking/defending
behavior, remaining goal/restart/rule edge cases, and end-to-end tactical validation.

Known simplifications still include:

- A point ball and discrete/abstract endpoints, with no continuous ball flight,
  height, spin, or full player collision model.
- No woodwork/own-goal pipeline or complete direct-restart scoring rules.
- Offside covers represented involvement, not off-ball screening/interference.
- Set-piece positioning is provisional; encroachment, retakes, countdowns, and
  complete restart legality are unfinished.
- No general added-time model, temporary injury treatment/return, or longer-term
  injury recovery system.
- Formation changes, individual roles and a full tactical decision system remain
  unfinished. There is no home-advantage model or demonstrated football realism.

**Calibration is deliberately reserved for the end of Milestone 1**, after the
intended features are in place. That includes probability constants, tactical and
fatigue effects, injury rates, attribute ranges/distributions, and aggregate match
realism. Current batches verify behavior and consistency rather than tune averages.

Interfaces, persistence, competitions, transfers and broader club management are
later work. The engine remains independent of a GUI or web application so those
systems can consume the same state and event APIs.
