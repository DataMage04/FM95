"""Reproducible aggregate calibration against StatsBomb match summaries.

Neutral synthetic teams measure pooled event rates, not real club predictions.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import json
from math import sqrt
from pathlib import Path
from statistics import mean, stdev

from fm95.match.mechanics.actions import ActionConfig
from fm95.match.mechanics.boundaries import OutOfPlayConfig
from fm95.match.mechanics.crossing import CrossConfig
from fm95.match.mechanics.defending import DefenseConfig
from fm95.match.mechanics.set_pieces import SetPieceConfig
from fm95.match.mechanics.shooting import ShotConfig

ROOT = Path(__file__).resolve().parents[2]
METRICS = ("goals", "shots", "shots_on_target", "passes_attempted", "passes_completed",
           "fouls_committed", "yellow_cards", "red_cards", "corners_taken",
           "penalties_taken", "penalties_scored", "woodwork_contacts", "shots_blocked")
CONFIGS = {"actions": ("action_config", ActionConfig), "defense": ("defense_config", DefenseConfig),
           "shots": ("shot_config", ShotConfig), "crossing": ("cross_config", CrossConfig),
           "boundaries": ("out_config", OutOfPlayConfig), "set_pieces": ("set_piece_config", SetPieceConfig)}


def profile_configs(profile):
    unknown = set(profile) - set(CONFIGS)
    if unknown:
        raise ValueError(f"Unknown calibration groups: {unknown}")
    return {argument: cls(**profile.get(group, {})) for group, (argument, cls) in CONFIGS.items()}


def load_profile():
    return json.loads((ROOT / "data/calibration/profile.json").read_text())["parameters"]


def simulate(job):
    from fm95.match.simulation import run_match
    from fm95.players.demo import demo_team
    from fm95.match import Match, Phase
    from fm95.match.systems.substitution_policy import AutoSubstitutionConfig
    from fm95.match.systems.timekeeping import AddedTimeConfig
    from fm95.match.mechanics.woodwork import WoodworkConfig
    from fm95.analysis.validation import validate_statistics
    seed, profile = job
    match = run_match(Match(demo_team("home", "Home", include_bench=True),
                            demo_team("away", "Away", include_bench=True), seed=seed,
                            auto_substitution_config=AutoSubstitutionConfig(enabled=True),
                            added_time_config=AddedTimeConfig(enabled=True),
                            woodwork_config=WoodworkConfig(enabled=True), **profile_configs(profile)))
    validate_statistics(match)
    if match.phase != Phase.FULL_TIME:
        raise AssertionError("Calibration match abandoned")
    sides = [asdict(match.statistics(t.id)) for t in (match.home, match.away)]
    return {**{k: sum(s[k] for s in sides) for k in METRICS},
            "elapsed_seconds": match.elapsed_seconds, "seed": seed}


def summary(rows):
    result = {}
    for metric in METRICS:
        values = [r[metric] for r in rows]
        average = mean(values)
        se = stdev(values)/sqrt(len(values)) if len(values)>1 else 0
        result[metric] = {"mean": average, "se": se,
                          "ci95": [max(0, average-1.96*se), average+1.96*se]}
    result["pass_completion"] = sum(r["passes_completed"] for r in rows)/sum(r["passes_attempted"] for r in rows)
    return result


def evaluate(profile, matches=32, seed=1000, workers=4):
    if type(matches) is not int or matches < 2:
        raise ValueError("At least two simulation matches required")
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(simulate, ((seed+i, profile) for i in range(matches))))
    return {"matches": matches, "seed": seed, "parameters": profile,
            "metrics": summary(rows), "rows": rows}


def loss(metrics, targets):
    # Relative errors with floors so rare red cards/penalties do not dominate.
    scales = {"goals": 1, "shots": 10, "shots_on_target": 3, "passes_attempted": 300,
              "passes_completed": 300, "fouls_committed": 10, "yellow_cards": 2,
              "red_cards": .25, "corners_taken": 5, "penalties_taken": .5}
    errors = [(metrics[k]["mean"]-targets[k]["mean"])/max(scales[k], targets[k]["mean"])
              for k in scales]
    return sqrt(mean(e*e for e in errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", type=int, default=100)
    parser.add_argument("--seed", type=int, default=9000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--parameters", type=Path, help="Replay a saved trial/profile JSON containing parameters")
    args = parser.parse_args()
    if args.baseline and args.parameters:
        parser.error("Choose baseline or a parameter file")
    profile = json.loads(args.parameters.read_text())["parameters"] if args.parameters else {} if args.baseline else load_profile()
    print(json.dumps(evaluate(profile, args.matches, args.seed, args.workers), indent=2))


if __name__ == "__main__":
    main()
