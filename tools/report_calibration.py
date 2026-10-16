"""Build the calibration report after freezing the training-selected profile."""
import argparse
import hashlib
import json
from math import sqrt
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fm95.analysis.calibration import loss
from fm95.match.mechanics.actions import ActionConfig, pass_completion_chance, shot_probabilities
from fm95.match.spatial.pitch import Zone, Direction


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--calibrated", type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text())
    calibrated = json.loads(args.calibrated.read_text())
    targets = json.loads((ROOT / "data/calibration/targets.json").read_text())
    profile = json.loads((ROOT / "data/calibration/profile.json").read_text())
    if calibrated["parameters"] != profile["parameters"]:
        raise ValueError("Evaluation does not match frozen profile")
    if baseline["parameters"] or baseline["seed"] != calibrated["seed"] or baseline["matches"] != calibrated["matches"]:
        raise ValueError("Baseline and profile must use identical independent seed sets")
    held = targets["groups"]["holdout"]["metrics"]
    comparisons = {}
    for key, target in held.items():
        if not isinstance(target, dict):
            continue
        sim = calibrated["metrics"][key]
        difference = sim["mean"]-target["mean"]
        combined_se = sqrt(sim["se"]**2+target["se"]**2)
        comparisons[key] = {"real_holdout": target, "baseline": baseline["metrics"][key],
                            "calibrated": sim, "difference": difference,
                            "within_combined_95_band": abs(difference)<=1.96*combined_se}
    actions = ActionConfig(**profile["parameters"]["actions"])
    sensitivity = []
    for attribute in (0, .25, .5, .75, 1):
        on, conversion = shot_probabilities(Zone(2, 1), actions, finishing=attribute, shot_stopping=.5)
        sensitivity.append({"attribute": attribute, "pass_completion": pass_completion_chance(Zone(1, 1), Zone(2, 1), Direction.RIGHT, actions, passing=attribute),
                            "shot_on_target": on, "goal_given_on_target": conversion,
                            "note": "Fixed-context response check; not estimated from player data"})
    code_hash = hashlib.sha256()
    for path in sorted((ROOT / "fm95").glob("*.py")):
        code_hash.update(path.name.encode()); code_hash.update(path.read_bytes())
    report = {"scope": "Pooled aggregate research calibration, neutral equal-ability balanced teams",
              "source": targets["source"], "revision": targets["revision"],
              "real_matches": {k: targets["groups"][k]["matches"] for k in ("train", "holdout")},
              "python": platform.python_version(), "engine_python_sha256": code_hash.hexdigest(),
              "simulation_matches_per_profile": calibrated["matches"], "independent_seed": calibrated["seed"],
              "baseline_loss": loss(baseline["metrics"], held), "calibrated_loss": loss(calibrated["metrics"], held),
              "loss_definition": "RMS of scaled mean errors across 10 declared metrics; floors documented in fm95.analysis.calibration.loss; descriptive, not a statistical pass threshold",
              "comparisons": comparisons,
              "pass_completion": {"real_holdout": held["pass_completion"], "baseline": baseline["metrics"]["pass_completion"], "calibrated": calibrated["metrics"]["pass_completion"]},
              "attribute_sensitivity": sensitivity, "unfitted": profile["unfitted"],
              "baseline_rows": baseline["rows"], "calibrated_rows": calibrated["rows"]}
    (ROOT / "docs/calibration-report.json").write_text(json.dumps(report, indent=2)+"\n")
    lines = ["# FM95 aggregate calibration — first pass", "", "Data source: **StatsBomb Open Data**, Premier League 2015/16.",
             "", "![StatsBomb](https://raw.githubusercontent.com/hudl/open-data/master/img/SB%20-%20Icon%20Lockup%20-%20Colour%20positive.png)",
             "", "280 chronological matches fit; the last 100 matches were reserved for validation. The profile was frozen before examining holdout statistics. Baseline and fitted profiles each ran 100 independent simulation seeds (9000–9099). Training used shared seed prefixes beginning at 1000.",
             "", "## Independent validation", "", "All figures below are totals per match across both teams.", "",
             "| Metric | Real holdout | Prototype | Fitted | Fitted 95% mean interval |", "| --- | ---: | ---: | ---: | ---: |"]
    for key, c in comparisons.items():
        sim=c["calibrated"]
        lines.append(f"| {key} | {c['real_holdout']['mean']:.3f} | {c['baseline']['mean']:.3f} | {sim['mean']:.3f} | {sim['ci95'][0]:.3f}–{sim['ci95'][1]:.3f} |")
    pc = report["pass_completion"]
    lines += ["", f"Ordinary pass completion: real {pc['real_holdout']:.1%}; prototype {pc['baseline']:.1%}; fitted {pc['calibrated']:.1%}.",
              "", f"Scaled RMS mean discrepancy: {report['baseline_loss']:.3f} → {report['calibrated_loss']:.3f}. This score is descriptive; it does not establish complete realism.",
              "", "Intervals use match-level standard errors and a normal approximation. Rare cards/penalties have substantial uncertainty; intervals are not exact count intervals. The JSON includes real-data uncertainty and combined-error comparisons. Multiple comparisons are descriptive, without a family-wise significance claim.",
              "", "Remaining discrepancies: goals are still elevated (3.28 versus 2.90). Fouls and red cards fall outside the descriptive combined 95% bands; red cards are too infrequent. All 30 simulated validation penalties scored, so aggregate penalty success is unstable despite a lower underlying conversion probability. These are reported without retuning on the holdout. A future tuning round needs a fresh validation sample. Keep this as an opt-in research preset rather than replacing prototype defaults.",
              "", "## Interpretation and limits", "", "Parameters were adjusted sequentially by manual moment matching on training statistics. Every trial, parameter set, sample size and training loss is recorded in calibration-training.json. This is not a global optimum search. Unequal trial sizes make small training-loss differences noisy.",
              "", "Ordinary passes exclude StatsBomb cross-tagged passes to match FM95's separate cross counters. Shot targets include Goal, Saved and Saved to Post; blocked shots and Saved Off Target are excluded. Cards include the second yellow as a yellow and a red. Periods 1–2 only; source goals use final scores, including own goals. All counted Foul Committed events are included, so provider treatment of advantage can differ from published summary totals. Corners count taken passes/direct shots, not awarded corners.",
              "", "Area and booked-player multipliers control foul generation, not the legality or sanction after an offence. They compensate for the prototype's spatial/challenge abstraction and are model-specific fitted coefficients, not measured behavioural effects.",
              "", "The fitted profile uses balanced equal-ability synthetic teams, optional added time/woodwork and automatic substitutions; generated injuries and automatic off-ball screening are disabled for fitting. Tactical and attribute stress are separate consistency checks. Historical league mix, unequal real teams, and the absence of home advantage limit result-distribution comparisons.",
              "", "Attribute sensitivity checks verify bounded, monotonic fixed-context responses. Aggregate match data cannot identify a unique player rating scale or skill-response slope. The normalized 0–1 range and response strength remain provisional. Fatigue, injuries, tactical effects, added-time durations and player distributions are not empirically fitted in this pass. Model xG remains the engine's probability output, not a fitted external shot-level xG model.",
              "", "## Reproduce", "", "```sh", "python tools/build_calibration_data.py", "python -m fm95.analysis.calibration --baseline --matches 100 --seed 9000 > baseline.json", "python -m fm95.analysis.calibration --matches 100 --seed 9000 > fitted.json", "python tools/report_calibration.py --baseline baseline.json --calibrated fitted.json", "python -m fm95.match.simulation --profile pl2015 --matches 20 --seed 95 --json", "python -m fm95.analysis.validation --profile pl2015 --matches 8 --seed 5000 --json", "```", "", "The source revision and per-event-file hashes are pinned in data/calibration/targets.json. Raw events and per-match source summaries stay in the ignored local cache; only aggregate analysis and a hash manifest are tracked. See the upstream [StatsBomb terms](https://github.com/hudl/open-data/blob/master/LICENSE.pdf); this is an analysis/research profile and is not a grant of commercial data rights.", ""]
    (ROOT / "docs/calibration.md").write_text("\n".join(lines))
    print(json.dumps({"baseline_loss": report["baseline_loss"], "calibrated_loss": report["calibrated_loss"],
                      "means": {k: [v["real_holdout"]["mean"],v["baseline"]["mean"],v["calibrated"]["mean"]] for k,v in comparisons.items()}}, indent=2))


if __name__ == "__main__":
    main()
