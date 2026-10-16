# FM95

A Python football manager built from the match engine outward. **Milestone 1 is
still in progress:** the engine now runs reproducible spatial match prototypes,
with a first real-data aggregate calibration profile. Attribute effects and several
other systems still need empirical calibration.

Python 3.10 or newer; no external runtime dependencies.

## Run and verify

```sh
python main.py
python -m unittest discover -s tests -v
python -m fm95.batch --matches 2 --seed 95 --json
python -m fm95.validation --matches 8 --seed 95 --json
```

The demo uses synthetic equal-ability teams, different tactical instructions,
automatic substitutions, and opt-in injury generation. It prints sample actions,
shots, restarts, substitutions, and statistics. The current regression suite has
**319 tests**.

A batch defaults to balanced tactics with automatic management and random injuries
disabled. Enable those features explicitly:

```sh
python -m fm95.batch --matches 2 --injuries --auto-substitutions --json
python -m fm95.batch --matches 2 --home-style pressing --away-style direct --json
```

The example styles are `balanced`, `pressing`, `possession`, and `direct`. They are
provisional configurations for exploring behavior, not validated tactical advice.
Use `python -m fm95.batch --help` for isolation switches. Optional cumulative
features can be exercised together:

```sh
python -m fm95.batch --matches 2 --seed 95 --added-time --woodwork --temporary-injuries --off-ball-offside --auto-substitutions --json
```

## Implemented foundations

| Area | Current behavior |
| --- | --- |
| Lifecycle | One-second clock, first half, explicit halftime pause/resume, reversed ends, full time, abandonment |
| Players and squads | Immutable player identities, assigned positions, 11-player starting lineups, named benches, active-player views |
| Spatial state | Metric pitch geometry, precise normalized ball/player locations, formation targets, coarse 3-by-3 context zones |
| Possession | Controlled, loose/aerial, and pending-restart states; recovery contests and possession accounting |
| Passing | Completed, intercepted, loose, out-of-play, and offside deliveries; forward runs, through balls, and tactical long passes |
| Defending | Closing down, distinct marking, coordinated cover behind the press, pressure, tackles, fouls, and shot blocks |
| Shooting | Shot goals, deflection/own goals, held saves, misses, parries, optional woodwork, rebounds and headers; scoring probabilities and model xG |
| Crossing | Open-play/corner deliveries, aerial contests, headers, headed clearances, keeper claims and punches |
| Restarts | Boundary/foul/injury restarts; direct-scoring and ordinary second-touch restrictions; clearance, penalty and wall setup |
| Offside | Position snapshots at the teammate's touch, checked at receptions, recoveries, aerial challenges and represented off-ball interference |
| Discipline | Yellow cards, second yellows, straight reds, active-player exclusion, emergency keepers, minimum-player handling |
| Substitutions | Single/grouped changes at stoppages and halftime, configurable limits/opportunities, no return substitutions |
| Condition | Stamina-dependent depletion, represented movement costs, stoppage/halftime recovery, effective abilities and movement limits |
| Management | Read-only fatigue recommendations and optional automatic fatigue/injury replacements |
| Injuries | Optional open-play/foul incidents, withdrawals, temporary treatment/return, replacement recommendations, short-handed play |
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
The default regulation baseline is 5400 seconds. A pending penalty, including a
required retake, resolves before the period ends; the second half retains its full
2700 seconds after any first-half extension.

`AddedTimeConfig(enabled=True)` (batch `--added-time`) compensates actual consumed
stoppage delays per half. `delay_play` supports explicit delays and `period_timing`
returns an immutable timing snapshot. The announced minimum can increase for
further lost time; overlapping delays are not double-counted. Halftime management
is excluded. Delay constants and rounding remain provisional.

For completed matches, controlled seconds + loose-ball seconds + dead-ball
seconds equal actual elapsed match time, including extensions. Possession percentages use controlled time only. Legacy
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
supports deterministic scenarios. Optional `WoodworkConfig(enabled=True)` represents near/far-post and crossbar
contacts, followed by a goal or rebound. These are discrete contact outcomes;
continuous height and flight remain abstract.

Shot events retain intended aim. An immediately represented on-target shot
deflected into goal is credited to its shooter by replacing the original shot
outcome; an off-target shot deflected into the defender's goal remains an own goal.
`goal_attribution` records the deflector without adding a second shot or extra xG.
Independent clearance/punch goals retain their separate attribution path.
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
pending restart/kickoff. Explicit `PenaltyIncident` inputs adjudicate accidental
double touches, relevant encroachment, keeper-line offences, backwards kicks,
illegal feints and wrong kickers. Voided attempts do not count as shots or xG;
retakes, indirect free kicks and represented warnings/cards follow the decision.

`handle_ball` accepts an adjudicated handling incident. Keeper handling tracks
intended teammate backpasses, direct teammate throws and rehandling after release.
An attempted release kick has its own exception. Actual hand control is separate
from foot possession: a countdown precedes the eight-second violation, which
awards a corner, with repeat sanctions. `restart_offence` handles represented
wall-distance, deliberate blocking, foul throws, delay and moving-ball incidents;
a quick interception is permitted. These observer APIs do not infer body/arm
legality or invent random offence frequencies.
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
The default injury remains a withdrawal for the remainder of the match.
`injure_player(team_id, player_id)` also supports deterministic scenarios even when
random generation is disabled. `injury(team_id, player_id)` exposes current withdrawal state; `injury_history`
preserves incidents after recovery.
Existing foul/boundary restarts take precedence; other injury stoppages award a
short dropped-ball restart, with the defending keeper receiving drops in their area.

Temporary treatment is optional: use `treat_player` or configure
`InjuryConfig.temporary_probability` (batch `--temporary-injuries` uses a provisional
.5 mixture). The default treatment wait is 60 running-clock seconds after restart.
Eligible returns represent referee permission and enter from the touchline;
halftime, keeper and represented quick-treatment exceptions are supported.
Off-field players recover without playing-time credit. Substitution cancels return,
and dismissed players cannot return.

Automatic managers prioritise injury replacements over fatigue changes, without
waiting for fatigue thresholds or minimum playing time. Manual managers can replace
withdrawn players at the stoppage. If limits/bench options prevent a change, teams
can continue short-handed with an emergency keeper if needed. Fewer than seven
available players prevents continued play; a manager may restore seven through a
legal injury replacement before the next step.

Off-ball offside involvement can be supplied with `report_offside_involvement`
for screening, challenges, attempts or obstruction with an explicit impact flag.
Optional `OffsideConfig.screening_enabled` (batch `--off-ball-offside`) adds a narrow
point-player vision-corridor proxy near the keeper before a shot. Mere offside
position is not penalized; saved/woodwork rebounds retain the original snapshot.
This is not a continuous body or vision model.

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
  second-touch offences + other represented indirect rule offences. These causes
  have separate counters.
- Model xG = the sum of recorded unconditional shot-scoring probabilities,
  including blocked/saved/missed/woodwork attempts.

Model xG describes this engine's assumptions; it is not an empirical expected-goals
model. Batch match i uses seed + i, retains aggregates rather than full event logs,
and reports completed/abandoned matches separately. JSON includes both teams'
instructions, feature configurations, scoreline frequencies, and mean statistics.
The same seed reproduces results for the same inputs, engine version and runtime;
changing instructions or features can change all subsequent random draws.

## Real-data calibration (first pass)

`--profile pl2015` selects an opt-in aggregate research profile fitted to
**StatsBomb Open Data, Premier League 2015/16**. The first 280 chronological matches
were used for fitting; the final 100 were held out. Eight sequential training
trials are recorded. The frozen profile and prototype were then each evaluated
on 100 independent simulation seeds (9000–9099).

```sh
python -m fm95.batch --profile pl2015 --matches 20 --seed 95 --json
python -m fm95.calibration --matches 100 --seed 9000 > fitted.json
python -m fm95.validation --profile pl2015 --matches 8 --seed 5000 --json
```

The profile enables added time, woodwork and automatic substitutions, matching
its fitting setup. Other feature/isolation flags still work. Defaults remain
available with `--profile prototype`. Python callers can pass
`**profile_configs(load_profile())` from `fm95.calibration` into `Match`, alongside
those three feature configurations.

| Totals per match | Real holdout | Prototype | Fitted profile |
| --- | ---: | ---: | ---: |
| Goals | 2.90 | 3.73 | 3.28 |
| Shots | 26.57 | 31.56 | 25.77 |
| Shots on target | 8.67 | 9.05 | 8.92 |
| Ordinary passes | 941.10 | 600.71 | 941.87 |
| Fouls | 24.97 | 18.78 | 23.69 |
| Yellow cards | 3.01 | 3.86 | 3.12 |
| Red cards | 0.17 | 0.50 | 0.07 |
| Corners taken | 11.11 | 7.77 | 10.64 |
| Penalties taken | 0.28 | 2.01 | 0.30 |

Ordinary passes exclude cross-tagged source passes to match the engine's separate
cross counters. Foul generation now supports area and booked-player caution
multipliers; actual offence and sanction rules remain intact. These are fitted
model coefficients, not measured causal behaviour.

See [the full calibration report](docs/calibration.md),
[validation measurements and uncertainty](docs/calibration-report.json),
[training trials](docs/calibration-training.json), and
[pinned source targets/hash manifest](data/calibration/targets.json).
Data attribution: **StatsBomb**, [Open Data](https://github.com/hudl/open-data).

![StatsBomb](https://raw.githubusercontent.com/hudl/open-data/master/img/SB%20-%20Icon%20Lockup%20-%20Colour%20positive.png)

This first pass improves aggregate rates but is incomplete: goals remain high,
fouls and reds miss the descriptive combined uncertainty bands, and penalty
conversion remains noisy. The held-out data was not used for further tuning.
The source terms support research/analysis; this preset does not grant commercial
data rights. Raw events stay in the ignored local cache.

## Milestone 2: player and team differences

Milestone 2's player-differentiation foundation is implemented and integrated-tested.
The reproducible synthetic squad generator creates an 18-player roster (4-3-3 starting
XI plus seven substitutes), varies individual execution skills, and adds provisional
position aptitudes for goalkeepers, defenders, fullbacks, midfielders, creators,
wingers and strikers. It stores no overall rating.

```sh
python -m fm95.batch --generated-squads --home-strength .7 --away-strength .3 --decision-strength .7 --matches 20 --seed 95 --json
```

The seed and player identifiers determine each player's attributes, so rerunning the
same setup reproduces the squad. The strength controls shift the synthetic team's
mean attribute level; they are experiment controls, not calibrated ratings or
estimates for real clubs. Existing `demo_team()` remains the neutral equal-ability
fixture for match-engine checks. Player decisions have immutable tendencies for
shooting, dribbling, crossing, through balls, pass directness and pressing. They bias
choices after team instructions, while attributes still resolve execution. Pressing
tendency affects a defender's willingness to attempt a press, not the chance of
winning one. Set `--decision-strength 0` to isolate the neutral decision layer;
the default `.5` is provisional. Substitutes retain their own generated tendencies.

The integrated acceptance command exercises generated players, tactics, substitutions,
temporary treatment and return, dismissal, added time, woodwork, off-ball screening,
low/high synthetic team strengths, statistical reconciliation and exact seeded replay:

```sh
python -m fm95.validation --matches 8 --seed 95 --generated-squads --decision-strength .8 --json
```

The checked-in [Milestone 2 validation report](docs/milestone2-validation.json) records
eight completed scenarios, 16 simulations, 91,226 state checks, 4,827 player decision
events, 1,603 press attempts and 52 substitutions. This validates implementation
consistency and determinism, not empirical football realism. Player attribute and
tendency distributions remain synthetic and uncalibrated; later work can fit their
ranges and effects to suitable player-level data.

## Remaining Milestone 1 work

The requested goal-handling, represented rules, treatment/off-ball interactions
and integrated validation stages are implemented. The first aggregate calibration
pass is available; remaining work includes further goal/discipline validation on
fresh data, contextual shot quality, and attribute-range/effect refinement.

The integrated runner checks state invariants each tick, statistical reconciliation,
immutable squad data and exact seeded replay. It combines tactical changes,
substitutions, a dismissal, treatment/return, added time, woodwork and off-ball
screening, including attribute-range stress cases. The committed
[validation report](docs/integrated-validation.json) records eight completed
scenarios, 16 simulations and 91,234 state checks. This verifies consistency and
determinism, not football realism or exhaustive feature combinations.

Known simplifications still include:

- A point ball and discrete/abstract endpoints, with no continuous ball flight,
  height, spin, or full player collision model.
- Explicit observer inputs for several referee incidents, rather than automatic
  physical detection of every offence; no claim of complete rule coverage.
- A geometric screening proxy and immediate represented deflection attribution.
- Temporary match treatment, without a longer-term injury recovery system.
- No complete tactical decision system, home-advantage model, or demonstrated
  aggregate football realism.

**Milestone 1 calibration is still in progress.** The aggregate research profile
fits action pace, passing, shots, foul/card and penalty rates. Tactical and fatigue
effects, injury rates, added-time durations, player attribute ranges/distributions
and response strength are not empirically identified by these aggregate targets.
Bounded monotonic attribute responses have been checked, but that does not validate
a final player-rating scale or realistic skill effects.

## Milestone 3: in-memory competitions and seasons

Milestone 3 adds an in-memory home-and-away league season. It generates fixtures
and matchdays for even or odd numbers of clubs, assigns a reproducible seed to
each fixture, runs matches using the existing match engine, records full-time
scores and statistics, and derives standings by points, goal difference, goals
scored and team ID. Matchdays progress in order; a partially played day can be
resumed, while completed results cannot be overwritten. The competition layer
does not add persistence, transfers or a user interface.

```python
from fm95.demo import demo_team
from fm95.season import Season

clubs = [demo_team("north", "North"), demo_team("south", "South")]
season = Season("2026/27", clubs, seed=95)
for matchday in season.matchdays:
    season.play_matchday(matchday)
print(season.standings())
```

See [the Milestone 3 guide](docs/milestone3.md) for the API behavior and
limitations. Persistence, transfers, broader club management and a GUI remain
future work; the competition layer is in memory and reuses the engine's seeded
pseudo-random behavior for repeatable fixture simulation.

Run the full-season acceptance check with `python -m fm95.season_validation
--clubs 4 --seed 95 --json`; its recorded output is in
[docs/milestone3-validation.json](docs/milestone3-validation.json).
