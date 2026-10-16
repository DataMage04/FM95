"""Run a compact full-season acceptance check: python -m fm95.competition.validation."""

import argparse
from dataclasses import asdict
import json

from fm95.players.demo import demo_team
from fm95.competition.season import Season


def run_season_validation(*, clubs: int = 4, seed: int = 95) -> dict:
    if type(clubs) is not int or clubs < 2:
        raise ValueError("Club count must be an integer of at least two.")
    if type(seed) is not int:
        raise ValueError("Seed must be an integer.")
    teams = [demo_team(f"club-{index + 1}", f"Club {index + 1}")
             for index in range(clubs)]
    season = Season("validation", teams, seed=seed)
    matchday_results = []
    for matchday in season.matchdays:
        results = season.play_matchday(matchday)
        season.validate()
        matchday_results.append({"matchday": matchday, "fixtures_completed": len(results)})
    standings = season.standings()
    expected_played = 2 * (clubs - 1)
    if not season.complete or len(season.results) != clubs * (clubs - 1):
        raise AssertionError("Season did not complete its home-and-away schedule.")
    if any(row.played != expected_played for row in standings):
        raise AssertionError("Not every club has the expected number of played fixtures.")
    if sum(row.won for row in standings) != sum(row.lost for row in standings):
        raise AssertionError("League wins and losses do not reconcile.")
    if sum(row.drawn for row in standings) % 2:
        raise AssertionError("League draws do not reconcile in pairs.")
    return {
        "passed": True,
        "purpose": "full-season schedule, execution, result and table consistency",
        "seed": seed,
        "clubs": clubs,
        "fixtures": len(season.fixtures),
        "completed_fixtures": len(season.results),
        "matchdays": matchday_results,
        "standings": [asdict(row) for row in standings],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clubs", type=int, default=4)
    parser.add_argument("--seed", type=int, default=95)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_season_validation(clubs=args.clubs, seed=args.seed)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Passed: {result['completed_fixtures']} fixtures across "
              f"{result['clubs']} clubs and {len(result['matchdays'])} matchdays.")


if __name__ == "__main__":
    main()
