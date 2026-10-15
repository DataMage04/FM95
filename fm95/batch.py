"""Run reproducible synthetic matches: python -m fm95.batch --matches 200."""

import argparse
from collections import Counter
from dataclasses import asdict
import json

from fm95.actions import ActionConfig
from fm95.demo import demo_team
from fm95.match import Match, Phase


def run_match(match: Match) -> Match:
    """Run a fresh match to full time, automatically resuming halftime."""
    match.start()
    while match.phase != Phase.FULL_TIME:
        if match.phase == Phase.HALF_TIME:
            match.resume()
        else:
            match.step()
    return match


def run_batch(matches: int = 200, seed: int = 95,
              config: ActionConfig | None = None) -> dict:
    """Match i uses seed+i; retain aggregates only, not every match's event log."""
    if type(matches) is not int or matches < 1:
        raise ValueError("Match count must be a positive integer.")
    if type(seed) is not int:
        raise ValueError("Base seed must be an integer.")
    config = config if config is not None else ActionConfig()
    teams = (demo_team("home", "Home"), demo_team("away", "Away"))
    totals = {team.id: Counter() for team in teams}
    outcomes, scorelines = Counter(), Counter()
    for index in range(matches):
        match = run_match(Match(*teams, seed=seed + index, action_config=config))
        for team in teams:
            values = asdict(match.statistics(team.id))
            values.pop("team_id")
            totals[team.id].update(values)
        home_goals, away_goals = match.home_goals, match.away_goals
        outcomes["home_win" if home_goals > away_goals else
                 "away_win" if away_goals > home_goals else "draw"] += 1
        scorelines[f"{home_goals}-{away_goals}"] += 1
    averages = {}
    for team_id, total in totals.items():
        averages[team_id] = {key: value / matches for key, value in total.items()}
        averages[team_id]["pass_completion_percentage"] = (
            100 * total["passes_completed"] / total["passes_attempted"]
            if total["passes_attempted"] else 0.0
        )
    return {
        "matches": matches, "base_seed": seed, "configuration": asdict(config),
        "outcomes": {key: outcomes[key] for key in ("home_win", "draw", "away_win")},
        "average_total_goals": averages["home"]["goals"] + averages["away"]["goals"],
        "team_averages": averages, "scorelines": dict(sorted(scorelines.items())),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", type=int, default=200)
    parser.add_argument("--seed", type=int, default=95)
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary")
    args = parser.parse_args()
    if args.matches < 1:
        parser.error("--matches must be positive")
    summary = run_batch(args.matches, args.seed)
    if args.json:
        print(json.dumps(summary, indent=2))
        return
    print(f"{args.matches} matches; seeds {args.seed}–{args.seed + args.matches - 1}")
    print(f"Outcomes: {summary['outcomes']}")
    print(f"Mean total goals: {summary['average_total_goals']:.2f}")
    for side, stats in summary["team_averages"].items():
        print(f"{side}: goals={stats['goals']:.2f}, shots={stats['shots']:.2f}, "
              f"on target={stats['shots_on_target']:.2f}, "
              f"passes={stats['passes_attempted']:.2f}, "
              f"completion={stats['pass_completion_percentage']:.1f}%, "
              f"possession={stats['possession_percentage']:.1f}%")
    print("Synthetic baseline; probabilities are uncalibrated. Use --json for all metrics.")


if __name__ == "__main__":
    main()
