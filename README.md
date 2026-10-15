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
location at the event time. The demo still has no autonomous football actions.

## Next increments within milestone 1

1. Add action selection and pass/turnover resolution, initially with equal players.
2. Add shots and goalkeeper outcomes; goals update both state and event log.
3. Introduce attributes only where an implemented action needs them.
4. Add restarts, tactics and match statistics, then calibrate batch simulations.

Keep the engine independent of interfaces and persistence. Future text,
desktop or web interfaces should consume the same match state and events.
