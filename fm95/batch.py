"""Run reproducible synthetic matches: python -m fm95.batch --matches 200."""

import argparse
from collections import Counter
from dataclasses import asdict
import json

from fm95.actions import ActionConfig
from fm95.defending import DefenseConfig
from fm95.demo import demo_team
from fm95.match import Match, Phase


def run_match(match: Match) -> Match:
    """Run a fresh match to full time, automatically resuming halftime."""
    match.start()
    while match.phase not in (Phase.FULL_TIME, Phase.ABANDONED):
        if match.phase == Phase.HALF_TIME:
            match.resume()
        else:
            match.step()
    return match


def run_batch(matches: int = 200, seed: int = 95,
              config: ActionConfig | None = None, defense_config: DefenseConfig | None = None) -> dict:
    """Match i uses seed+i; retain aggregates only, not every match's event log."""
    if type(matches) is not int or matches < 1:
        raise ValueError("Match count must be a positive integer.")
    if type(seed) is not int:
        raise ValueError("Base seed must be an integer.")
    config = config if config is not None else ActionConfig()
    defense_config = defense_config if defense_config is not None else DefenseConfig()
    teams = (demo_team("home", "Home"), demo_team("away", "Away"))
    initial = Match(*teams)
    totals = {team.id: Counter({key: 0 for key in asdict(initial.statistics(team.id))
                               if key != "team_id"}) for team in teams}
    outcomes, scorelines = Counter(), Counter()
    completed = 0
    for index in range(matches):
        match = run_match(Match(*teams, seed=seed + index, action_config=config,
                                defense_config=defense_config))
        if match.phase == Phase.ABANDONED:
            outcomes["abandoned"] += 1
            continue
        completed += 1
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
        averages[team_id] = {key: value / completed if completed else 0.0
                             for key, value in total.items()}
        averages[team_id]["pass_completion_percentage"] = (
            100 * total["passes_completed"] / total["passes_attempted"]
            if total["passes_attempted"] else 0.0
        )
    return {
        "matches": matches, "completed_matches": completed,
        "base_seed": seed, "configuration": asdict(config),
        "defense_configuration": asdict(defense_config),
        "outcomes": {key: outcomes[key] for key in ("home_win", "draw", "away_win", "abandoned")},
        "average_total_goals": averages["home"]["goals"] + averages["away"]["goals"],
        "team_averages": averages, "scorelines": dict(sorted(scorelines.items())),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", type=int, default=200)
    parser.add_argument("--seed", type=int, default=95)
    parser.add_argument("--context-strength", type=float, default=1.0,
                        help="Situational effects from 0 (neutral) to 1 (default)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary")
    parser.add_argument("--no-defense", action="store_true", help="Disable spatial defense for isolation")
    args = parser.parse_args()
    if args.matches < 1:
        parser.error("--matches must be positive")
    if not 0 <= args.context_strength <= 1:
        parser.error("--context-strength must be between 0 and 1")
    summary = run_batch(args.matches, args.seed, ActionConfig(context_strength=args.context_strength),
                        DefenseConfig(enabled=not args.no_defense))
    if args.json:
        print(json.dumps(summary, indent=2))
        return
    print(f"{args.matches} matches; seeds {args.seed}–{args.seed + args.matches - 1}")
    print(f"Outcomes: {summary['outcomes']}")
    print(f"Mean total goals: {summary['average_total_goals']:.2f}")
    for side, stats in summary["team_averages"].items():
        print(f"{side}: goals={stats['goals']:.2f}, model xG={stats['expected_goals']:.2f}, "
              f"shots={stats['shots']:.2f}, "
              f"on target={stats['shots_on_target']:.2f}, "
              f"passes={stats['passes_attempted']:.2f}, "
              f"completion={stats['pass_completion_percentage']:.1f}%, "
              f"possession={stats['possession_percentage']:.1f}%, "
              f"take-ons={stats['dribbles_attempted']:.2f}, tackles won={stats['tackles_won']:.2f}, "
              f"fouls={stats['fouls_committed']:.2f}, "
              f"cards={stats['yellow_cards']:.2f}Y/{stats['red_cards']:.2f}R, "
              f"presses won={stats['presses_won']:.2f}/{stats['presses_attempted']:.2f}")
    print(f"Averages and scorelines cover {summary['completed_matches']} completed matches.")
    print("Synthetic baseline; probabilities are uncalibrated. Use --json for all metrics.")


if __name__ == "__main__":
    main()
