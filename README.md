# FM95

A Python football manager, developed from the match engine outward.

## Run

Python 3.10 or newer. No external dependencies for the foundation.

```sh
python main.py
python -m unittest discover -s tests -v
```

## Milestone 1, foundation

This increment implements player identity, starting lineups, teams, the match
lifecycle, a one-second simulation clock, and timestamped lifecycle events.
Lineups require 11 unique players and exactly one goalkeeper. Player IDs must
also be unique across the two teams.

`Match.start()` begins the first half. Each `step()` advances one simulated
second, independent of real time. At 45 minutes the engine pauses;
`resume()` starts the second half. At 90 minutes the match ends.
The demo automatically resumes halftime. Added time is deferred.

The prototype now includes passing, interceptions, shots, goals and basic restarts.
Goalkeeper is a lineup designation; there are deliberately no overall ratings or
performance attributes yet.

## Possession foundation

The ball uses a fixed 3-by-3 pitch grid. Columns 0–2 run left to right;
lanes 0–2 run bottom to top. Centre is `(1, 1)`. These are coarse ball
locations, not player coordinates. Lane numbers stay fixed when teams switch ends.

Home attacks right in the first half, away attacks left. Directions reverse
when the second half starts. `zone.third_for(match.attacking_direction(team_id))`
converts a fixed location into that team's defensive, middle or attacking third.

`match.possession` contains the team ID, carrier ID and zone together, or is
`None` before kickoff, at halftime and at full time. Kickoff assigns the ball
at centre to the first outfield player in lineup order, a temporary convention.
`set_possession(team_id, player_id, zone)` validates and records a resolved
ownership/location change. It will be used by future football actions; it does
not simulate a pass, tackle, ball trajectory or loose ball itself.

Kickoff and possession events also carry the player and zone, preserving the
location at the event time.

## Autonomous passing baseline

`Match(..., seed=95)` uses a private random generator for reproducible runs.
Every six simulated seconds, the carrier attempts a pass to another outfield
teammate. The ball can stay in its current zone or move one neighbouring zone.
Legal forward destinations have weight 3; same-zone, lateral and backward choices
have weight 1 each. Teams use their current attacking direction.

Pass completion has a provisional base probability of 0.85, modified by context below.
Completed passes transfer ownership to the receiver. Every failed pass is currently
an interception by a randomly selected opposition outfield player at the intended
destination. There are no loose balls, out-of-play passes or player positions yet.
These simplifications establish state transitions; they are not calibrated football
statistics. Players are equally capable and goalkeepers are excluded as receivers
and interceptors in this baseline.

`ActionConfig(interval_seconds=6, completion_probability=0.85)` can be supplied
as `Match(..., action_config=config)`. Whistles take priority over actions; kickoff
resets the action timer. Seeded reproducibility assumes the same inputs, engine
version and Python runtime. Real-time display speed does not affect outcomes.

Each pass creates one `pass_completed` or `pass_intercepted` event. `team_id` and
`player_id` identify the passing team and passer; `receiver_id` is the intended
recipient, `interceptor_id` identifies the winner on failure, `origin` is the
starting zone, and `zone` is the destination. The CLI shows ten sample passes,
lifecycle events and pass totals.

## Shooting and restarts

On each action, an attacking-third carrier chooses to shoot with base probability
0.12; otherwise they pass. Defensive and middle-third carriers always pass.
A shot has base on-target probability 0.40 and base conditional goal probability
0.25, otherwise the goalkeeper holds it. Context modifies these values below.
With context disabled, goal probability per shot is 0.40 × 0.25 = 0.10.
These are uncalibrated design settings, not an empirical xG model.
Set `shot_probability`, `on_target_probability`, and
`goal_given_on_target_probability` on `ActionConfig` to change them.

Each attempt emits exactly one outcome: `goal`, `shot_saved` or `shot_missed`.
The event identifies the shooting team, shooter, shot zone and defending keeper
via `goalkeeper_id`. A goal increments the score and immediately emits a kickoff
for the conceding team at centre. A held save gives the keeper possession in the
centre lane of their defensive column. A miss emits an immediate `goal_kick`
event and gives the keeper possession at that same coarse location. The keeper
can distribute via a pass on the next action.

Restarts currently take no simulated time; shot events and resulting restarts
share a timestamp. Corners, blocks, rebounds, offside, restart delays and added
time are deferred. Whistles still prevent any action at exactly 45 or 90 minutes.
The CLI now includes all shots and restarts, with per-team attempts, shots on
target (goals plus saves), goals and passing totals derived from the event log.

## Next increments within milestone 1

### Situational probabilities and model xG

Actions now apply provisional multipliers to probability odds. For base probability
`p`, multiplier `m` and context strength `s`, the effective multiplier is
`f = 1 + s * (m - 1)` and the adjusted probability is `p*f / (1-p+p*f)`.
This preserves forced probabilities 0 and 1 and keeps all configured outcomes bounded.

Pass multipliers: forward 0.75, backward 1.20, same zone 1.25, lateral 1.00.
Passes originating in the attacking third apply an additional factor of 0.85 as
a coarse pressure proxy. This does not measure defender proximity or actual pass
distance. Direction is relative to the attacking team and switches at halftime.

Central-lane shot choice uses multiplier 1.25; wide lanes use 0.75. Central shots
use on-target multiplier 1.20 and conditional-goal multiplier 1.25; wide shots
use 0.80 and 0.70. Each shot records its adjusted on-target probability and
unconditional scoring probability before resolution. Every pass records its
adjusted completion probability. All players remain equally capable.

`TeamStats.expected_goals` sums scoring probabilities across all attempts,
including saves and misses. The CLI labels this **model xG**: it describes this
engine's assumptions, not a trained or validated real-world expected-goals model.
The coarse grid cannot yet represent shot distance, angle or defensive pressure.

Use `ActionConfig(context_strength=0)` to disable context or any value from 0 to 1
to interpolate its effect. Batch comparison:

```sh
python -m fm95.batch --matches 200 --seed 95 --context-strength 0
python -m fm95.batch --matches 200 --seed 95 --context-strength 1
```

Both runs start matches with identical seeds; changed outcomes can change later
random draws, so they do not preserve identical action sequences. Contextual
settings change the seeded results from earlier engine versions.

### Planned work

1. Add richer action context and introduce attributes where actions need them.
2. Expand restarts and tactics, then calibrate batch simulations.

## Match statistics and batch diagnostics

`match.statistics(team_id)` returns a fresh immutable `TeamStats` snapshot before,
during or after a match. It provides goals, attempted/completed passes, shots,
shots on target, saves, interceptions, possession seconds, possession percentage
and pass completion percentage. Event counts provide action statistics; a saved
opposition shot is credited as a save and an intercepted opposition pass as an
interception for the defending team.

Each clock step credits one second to the team holding possession at the start
of that step, before resolving the action or whistle at its end. Halftime accrues
no time. Possession seconds therefore total 5400 for a complete prototype match.
Percentages use elapsed credited time, with zero before any play. Instant restarts
consume no extra time. This convention will need refinement when loose balls,
ball flight and stoppage durations are introduced.

Run a repeatable diagnostic batch using synthetic equal-ability teams:

```sh
python -m fm95.batch --matches 200 --seed 95
python -m fm95.batch --matches 200 --seed 95 --json
```

Match i uses seed `95 + i` for i starting at zero. The runner retains aggregates
instead of all event logs. Summaries include configuration, result counts, scoreline
frequencies, mean goals and per-team mean statistics. Batch pass completion is
weighted across all attempted passes; possession percentage is the mean across
matches. JSON output supports later comparisons without parsing console text.
Programmatic callers can pass `config=ActionConfig(...)` to `run_batch` to compare
settings using the same seed range. These diagnostics do not establish realism
or a home advantage; the prototype currently has no home-advantage parameter.

Keep the engine independent of interfaces and persistence. Future text,
desktop or web interfaces should consume the same match state and events.
