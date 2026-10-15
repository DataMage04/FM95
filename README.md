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

The score remains 0–0 because no football actions exist yet. This is a lifecycle
demo, not a complete match simulation. Goalkeeper is a lineup designation;
there are deliberately no overall ratings or performance attributes yet.

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

Pass completion has a provisional probability of 0.85 for every player and zone.
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
lifecycle events and pass totals. Shots and goals remain pending.

## Next increments within milestone 1

1. Add pass-versus-shot selection and goalkeeper outcomes; goals update state and events.
2. Introduce attributes only where an implemented action needs them.
3. Add restarts, tactics and match statistics, then calibrate batch simulations.

Keep the engine independent of interfaces and persistence. Future text,
desktop or web interfaces should consume the same match state and events.
