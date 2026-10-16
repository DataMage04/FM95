"""Compare a saved, resumed season with an uninterrupted seeded run."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import tempfile

from fm95.competition.persistence import SAVE_VERSION, load_season, save_season
from fm95.competition.season import Season
from fm95.match.mechanics.actions import ActionConfig
from fm95.match.tactics import TeamTactics
from fm95.players.demo import demo_team


def run_save_resume_validation(*, clubs: int = 4, seed: int = 95) -> dict:
    if type(clubs) is not int or clubs < 2:
        raise ValueError("Club count must be an integer of at least two.")
    if type(seed) is not int:
        raise ValueError("Seed must be an integer.")
    teams = [demo_team(f"club-{index + 1}", f"Club {index + 1}", include_bench=True)
             for index in range(clubs)]
    options = {"action_config": ActionConfig(interval_seconds=90)}
    tactics = {
        team.id: TeamTactics(tempo=.65 + .05 * index, pressing=.55 + .05 * (index % 3))
        for index, team in enumerate(teams)
    }

    uninterrupted = Season("milestone4-validation", teams, seed=seed)
    interrupted = Season("milestone4-validation", teams, seed=seed)
    first_matchday = uninterrupted.matchdays[0]
    uninterrupted.play_matchday(first_matchday, match_options=options, tactics=tactics)
    interrupted.play_matchday(first_matchday, match_options=options, tactics=tactics)
    completed_before_save = len(interrupted.results)
    if not completed_before_save:
        raise AssertionError("Validation setup did not complete any fixtures before saving.")

    with tempfile.TemporaryDirectory(prefix="fm95-season-check-") as directory:
        path = save_season(interrupted, Path(directory) / "mid-season.json")
        resumed = load_season(path)
        saved_fixtures = resumed.fixtures
        saved_results = resumed.results
        saved_settings = resumed._run_settings
        resumed.validate()
        for matchday in resumed.matchdays:
            resumed.play_matchday(matchday)

    for matchday in uninterrupted.matchdays[1:]:
        uninterrupted.play_matchday(matchday)
    uninterrupted.validate()
    resumed.validate()
    checks = {
        "schedule_and_seeds_preserved": saved_fixtures == uninterrupted.fixtures,
        "completed_results_preserved_on_load": saved_results == interrupted.results,
        "settings_restored": saved_settings == interrupted._run_settings,
        "final_results_match": resumed.results == uninterrupted.results,
        "final_standings_match": resumed.standings() == uninterrupted.standings(),
        "all_fixtures_completed": resumed.complete,
    }
    if not all(checks.values()):
        raise AssertionError(f"Save/resume validation failed: {checks}")
    return {
        "passed": True,
        "purpose": "versioned save, restart, and deterministic season resumption",
        "save_version": SAVE_VERSION,
        "seed": seed,
        "clubs": clubs,
        "fixtures": len(resumed.fixtures),
        "completed_before_save": completed_before_save,
        "completed_after_resume": len(resumed.results) - completed_before_save,
        "matchdays": len(resumed.matchdays),
        "checks": checks,
        "standings": [asdict(row) for row in resumed.standings()],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clubs", type=int, default=4)
    parser.add_argument("--seed", type=int, default=95)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_save_resume_validation(clubs=args.clubs, seed=args.seed)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Passed: saved after {result['completed_before_save']} of "
              f"{result['fixtures']} fixtures; resumed season matches uninterrupted run.")


if __name__ == "__main__":
    main()
