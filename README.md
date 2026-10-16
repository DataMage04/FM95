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
**286 tests**.

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
| Defending | Closing down, distinct marking, coordinated cover behind the press, pressure, tackles, fouls, and shot blocks |
| Shooting | Shot goals, deflection/own goals, held saves, misses, parries, rebounds and headers; scoring probabilities and model xG |
| Crossing | Open-play/corner deliveries, aerial contests, headers, headed clearances, keeper claims and punches |
| Restarts | Boundary/foul/injury restarts; direct-scoring and ordinary second-touch restrictions; clearance, penalty and wall setup |
| Offside | Position snapshots at the teammate's touch, checked at represented receptions, recoveries, and aerial challenges |
| Discipline | Yellow cards, second yellows, straight reds, active-player exclusion, emergency keepers, minimum-player handling |
| Substitutions | Single/grouped changes at stoppages and halftime, configurable limits/opportunities, no return substitutions |
| Condition | Stamina-dependent depletion, represented movement costs, stoppage/halftime recovery, effective abilities and movement limits |
| Management | Read-only fatigue recommendations and optional automatic fatigue/injury replacements |
| Injuries | Optional open-play/foul incidents, match-ending withdrawals, replacement recommendations, short-handed play |
| Team tactics | Independent instructions, live formations and individual duties; attacking support, defensive cover and timed turnover responses |
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

## Live formations, duties and coordinated movement

Original squad `Player.position` values remain natural positions. `formation(team_id)`
returns a detached snapshot of current active assignments; `set_formation` requires
exactly those active players and preserves the current goalkeeper designation.
Reduced teams use reduced assignments. Formation changes move targets gradually,
preserve ball/restart state, and emit `formation_changed` events.

```python
from fm95.positions import Position
from fm95.roles import Duty

assignments = match.formation("home")
assignments["home-6"] = Position.AM
match.set_formation("home", assignments)
match.set_player_duty("home", "home-9", Duty.ATTACK)
```

Duties are `BALANCED`, `DEFEND`, `SUPPORT`, and `ATTACK`. They change intent and
selected action preferences, not base abilities. Substitutes inherit the outgoing
assignment and duty; keepers currently support balanced duty only. Duty changes
emit `player_duty_changed` events.

Attacking support offers up to two staggered outlets, prioritises support-duty
players and advances attack-duty runners. Defend-duty players and balanced centre
backs hold shape. Defending keeps one nearest presser, reserves a nearby covering
player where possible, and leaves others marking distinct opponents or holding
shape. Cover selection prioritises defend-duty players within its reach radius.

`match.transition` exposes an immutable turnover snapshot while active. The
provisional default window is 12 seconds, fading with match time: eligible
attackers advance and non-pressing defenders recover toward formation targets.
Another turnover reverses the response; same-team passes do not reset its timer.
Loose balls preserve prior ownership context, while restarts and kickoffs reset it.
All movement retains elapsed-time reach limits and fatigue costs.

`AttackConfig`, `DefenseConfig` and `TransitionConfig` expose these provisional
behaviors. Batch switches `--no-attacking-movement`, `--no-defensive-cover` and
`--no-transitions` isolate them. `--no-defense` retains the earlier spatial-movement
isolation convention, disabling this shared movement step as well.

## Goal and restart foundations

Represented blocks, parries, punches and clearances crossing the goal mouth now
score instead of always producing boundary restarts. `resolve_deflection_exit`
supports deterministic scenarios. Height and woodwork are not represented, and
own-goal attribution currently uses last touch rather than a full attribution model.
Resolved misses and failed open-play deliveries retain their abstract non-goal exits.

`restart_context` remembers the restart kind and taker until another player touches
the ball. An ordinary second touch awards an indirect free kick; receiving a dropped
ball permits repeated touches, but direct scoring still requires a second distinct
player. Direct throw-in/indirect-free-kick goals produce goal kicks; direct own-goal
entries from the represented restarts produce corners. Allowed direct goals from
kickoffs, corners, goal kicks and direct free kicks remain available to the resolver.
`record_ball_touch` and `resolve_restart_exit` support deterministic rule scenarios.
The development `set_possession` override clears restart-touch memory.

Restart setup corrects kickoff halves, opponent clearance, and penalty-area
exclusion for goal kicks/defensive free kicks. Other players stay 4 m from a dropped
ball; opponents stay 2 m from throw-ins and 9.15 m from free kicks, with the goal-line
exception represented. Since corner balls sit at the corner point, opponents are
placed 10.15 m from that point to clear the 1 m corner arc.

Penalty setup puts the keeper on the goal line and other players behind the mark,
outside the area and at least 9.15 m from the mark. Direct free-kick walls of at least
three defenders keep attackers at least 1 m away. The pending-penalty inspector and
execution share the same setup calculation. These are administrative placements,
adding no represented running distance or condition cost.

`restart_position_violations()` lists active players needing correction before a
pending restart/kickoff. Full retakes, encroachment sanctions, quick-restart
exceptions, handball and accidental penalty double-touch procedures are unfinished.
Rule references: [IFAB Law 8](https://www.theifab.com/laws/latest/the-start-and-restart-of-play/),
[Law 13](https://www.theifab.com/laws/latest/free-kicks/),
[Law 14](https://www.theifab.com/laws/latest/the-penalty-kick/), and
[Law 15](https://www.theifab.com/laws/latest/the-throw-in/),
[Law 16](https://www.theifab.com/laws/latest/the-goal-kick/) and
[Law 17](https://www.theifab.com/laws/latest/the-corner-kick/).

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
- Shots on target = goals - own goals received - other non-shot/deflection goals
  + opposition saves, including parries. `own_goals` counts goals conceded through
  the team's own last touch; `own_goals_received` counts the corresponding benefit.
- Indirect free kicks awarded to the opposition = offsides + represented restart
  second-touch offences. These causes have separate counters.
- Model xG = the sum of recorded unconditional shot-scoring probabilities,
  including blocked/saved/missed attempts.

Model xG describes this engine's assumptions; it is not an empirical expected-goals
model. Batch match i uses seed + i, retains aggregates rather than full event logs,
and reports completed/abandoned matches separately. JSON includes both teams'
instructions, feature configurations, scoreline frequencies, and mean statistics.
The same seed reproduces results for the same inputs, engine version and runtime;
changing instructions or features can change all subsequent random draws.

## Remaining Milestone 1 work

Next: **added-time and period-ending foundations**, followed by remaining goal,
restart and rule edge cases, and end-to-end tactical validation. Coordinated
movement and management are foundations, not a complete tactical decision system.

Known simplifications still include:

- A point ball and discrete/abstract endpoints, with no continuous ball flight,
  height, spin, or full player collision model.
- No woodwork or ball-height model; deflection/own-goal attribution is provisional.
- Offside covers represented involvement, not off-ball screening/interference.
- Administrative restart/penalty/wall setup is represented, but encroachment,
  retakes, countdowns, handball and complete restart legality remain unfinished.
- No general added-time model, temporary injury treatment/return, or longer-term
  injury recovery system.
- No complete tactical decision system, home-advantage model, or demonstrated
  aggregate football realism.

**Calibration is deliberately reserved for the end of Milestone 1**, after the
intended features are in place. That includes probability constants, tactical and
fatigue effects, injury rates, attribute ranges/distributions, and aggregate match
realism. Current batches verify behavior and consistency rather than tune averages.

Interfaces, persistence, competitions, transfers and broader club management are
later work. The engine remains independent of a GUI or web application so those
systems can consume the same state and event APIs.
