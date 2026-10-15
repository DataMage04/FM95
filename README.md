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

## Next increments within milestone 1

1. Define pitch zones, possession, ball carrier and attacking direction.
2. Add action selection and pass/turnover resolution, initially with equal players.
3. Add shots and goalkeeper outcomes; goals update both state and event log.
4. Introduce attributes only where an implemented action needs them.
5. Add restarts, tactics and match statistics, then calibrate batch simulations.

Keep the engine independent of interfaces and persistence. Future text,
desktop or web interfaces should consume the same match state and events.
