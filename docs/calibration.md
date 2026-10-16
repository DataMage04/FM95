# FM95 aggregate calibration — first pass

Data source: **StatsBomb Open Data**, Premier League 2015/16.

![StatsBomb](https://raw.githubusercontent.com/hudl/open-data/master/img/SB%20-%20Icon%20Lockup%20-%20Colour%20positive.png)

280 chronological matches fit; the last 100 matches were reserved for validation. The profile was frozen before examining holdout statistics. Baseline and fitted profiles each ran 100 independent simulation seeds (9000–9099). Training used shared seed prefixes beginning at 1000.

## Independent validation

All figures below are totals per match across both teams.

| Metric | Real holdout | Prototype | Fitted | Fitted 95% mean interval |
| --- | ---: | ---: | ---: | ---: |
| goals | 2.900 | 3.730 | 3.280 | 2.911–3.649 |
| shots | 26.570 | 31.560 | 25.770 | 24.759–26.781 |
| shots_on_target | 8.670 | 9.050 | 8.920 | 8.318–9.522 |
| passes_attempted | 941.100 | 600.710 | 941.870 | 937.756–945.984 |
| passes_completed | 736.000 | 414.530 | 745.770 | 741.223–750.317 |
| fouls_committed | 24.970 | 18.780 | 23.690 | 22.910–24.470 |
| yellow_cards | 3.010 | 3.860 | 3.120 | 2.788–3.452 |
| red_cards | 0.170 | 0.500 | 0.070 | 0.020–0.120 |
| corners_taken | 11.110 | 7.770 | 10.640 | 9.965–11.315 |
| penalties_taken | 0.280 | 2.010 | 0.300 | 0.206–0.394 |
| penalties_scored | 0.190 | 1.460 | 0.300 | 0.206–0.394 |
| woodwork_contacts | 0.530 | 0.810 | 0.520 | 0.379–0.661 |
| shots_blocked | 7.580 | 6.690 | 7.890 | 7.357–8.423 |

Ordinary pass completion: real 78.2%; prototype 69.0%; fitted 79.2%.

Scaled RMS mean discrepancy: 1.199 → 0.137. This score is descriptive; it does not establish complete realism.

Intervals use match-level standard errors and a normal approximation. Rare cards/penalties have substantial uncertainty; intervals are not exact count intervals. The JSON includes real-data uncertainty and combined-error comparisons. Multiple comparisons are descriptive, without a family-wise significance claim.

Remaining discrepancies: goals are still elevated (3.28 versus 2.90). Fouls and red cards fall outside the descriptive combined 95% bands; red cards are too infrequent. All 30 simulated validation penalties scored, so aggregate penalty success is unstable despite a lower underlying conversion probability. These are reported without retuning on the holdout. A future tuning round needs a fresh validation sample. Keep this as an opt-in research preset rather than replacing prototype defaults.

## Interpretation and limits

Parameters were adjusted sequentially by manual moment matching on training statistics. Every trial, parameter set, sample size and training loss is recorded in calibration-training.json. This is not a global optimum search. Unequal trial sizes make small training-loss differences noisy.

Ordinary passes exclude StatsBomb cross-tagged passes to match FM95's separate cross counters. Shot targets include Goal, Saved and Saved to Post; blocked shots and Saved Off Target are excluded. Cards include the second yellow as a yellow and a red. Periods 1–2 only; source goals use final scores, including own goals. All counted Foul Committed events are included, so provider treatment of advantage can differ from published summary totals. Corners count taken passes/direct shots, not awarded corners.

Area and booked-player multipliers control foul generation, not the legality or sanction after an offence. They compensate for the prototype's spatial/challenge abstraction and are model-specific fitted coefficients, not measured behavioural effects.

The fitted profile uses balanced equal-ability synthetic teams, optional added time/woodwork and automatic substitutions; generated injuries and automatic off-ball screening are disabled for fitting. Tactical and attribute stress are separate consistency checks. Historical league mix, unequal real teams, and the absence of home advantage limit result-distribution comparisons.

Attribute sensitivity checks verify bounded, monotonic fixed-context responses. Aggregate match data cannot identify a unique player rating scale or skill-response slope. The normalized 0–1 range and response strength remain provisional. Fatigue, injuries, tactical effects, added-time durations and player distributions are not empirically fitted in this pass. Model xG remains the engine's probability output, not a fitted external shot-level xG model.

## Reproduce

```sh
python tools/build_calibration_data.py
python -m fm95.analysis.calibration --baseline --matches 100 --seed 9000 > baseline.json
python -m fm95.analysis.calibration --matches 100 --seed 9000 > fitted.json
python tools/report_calibration.py --baseline baseline.json --calibrated fitted.json
python -m fm95.match.simulation --profile pl2015 --matches 20 --seed 95 --json
python -m fm95.analysis.validation --profile pl2015 --matches 8 --seed 5000 --json
```

The source revision and per-event-file hashes are pinned in data/calibration/targets.json. Raw events and per-match source summaries stay in the ignored local cache; only aggregate analysis and a hash manifest are tracked. See the upstream [StatsBomb terms](https://github.com/hudl/open-data/blob/master/LICENSE.pdf); this is an analysis/research profile and is not a grant of commercial data rights.
