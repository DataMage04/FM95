import json
from pathlib import Path
import tempfile
import unittest

from fm95.match.mechanics.actions import ActionConfig
from fm95.match.tactics import TeamTactics
from fm95.players.demo import demo_team
from fm95.competition.persistence import load_season, save_season
from fm95.competition.season import Season


def make_season():
    teams = [demo_team(f"club-{index}", f"Club {index}", include_bench=True)
             for index in range(4)]
    return Season("persistence-test", teams, seed=95, points_for_win=3,
                  points_for_draw=1, points_for_loss=0)


class SeasonPersistenceTests(unittest.TestCase):
    def test_round_trip_preserves_rosters_schedule_results_rules_settings_and_table(self):
        season = make_season()
        day = season.matchdays[0]
        options = {"action_config": ActionConfig(interval_seconds=90)}
        tactics = {season.teams[0].id: TeamTactics(tempo=.7, pressing=.8)}
        season.play_matchday(day, match_options=options, tactics=tactics)

        with tempfile.TemporaryDirectory() as directory:
            path = save_season(season, Path(directory) / "nested" / "save.json")
            loaded = load_season(path)

        self.assertEqual(loaded.name, season.name)
        self.assertEqual(loaded.seed, season.seed)
        self.assertEqual(loaded.teams, season.teams)
        self.assertEqual(loaded.fixtures, season.fixtures)
        self.assertEqual(loaded.results, season.results)
        self.assertEqual(loaded.standings(), season.standings())
        self.assertEqual(loaded._run_settings, season._run_settings)

    def test_partial_save_resume_matches_an_uninterrupted_seeded_season(self):
        uninterrupted = make_season()
        interrupted = make_season()
        options = {"action_config": ActionConfig(interval_seconds=90)}
        tactics = {
            uninterrupted.teams[0].id: TeamTactics(tempo=.7, pressing=.8),
            uninterrupted.teams[1].id: TeamTactics(width=.75, passing_directness=.65),
        }
        interrupted_tactics = {
            interrupted.teams[0].id: tactics[uninterrupted.teams[0].id],
            interrupted.teams[1].id: tactics[uninterrupted.teams[1].id],
        }

        uninterrupted.play_matchday(uninterrupted.matchdays[0], match_options=options, tactics=tactics)
        for day in uninterrupted.matchdays[1:]:
            uninterrupted.play_matchday(day)

        interrupted.play_matchday(interrupted.matchdays[0], match_options=options,
                                  tactics=interrupted_tactics)
        with tempfile.TemporaryDirectory() as directory:
            save_path = save_season(interrupted, Path(directory) / "season.json")
            resumed = load_season(save_path)
            original_fixture_seeds = tuple(fixture.seed for fixture in resumed.fixtures)
            self.assertEqual(len(resumed.results), len(resumed.fixtures_for_matchday(1)))
            for day in resumed.matchdays[1:]:
                resumed.play_matchday(day)

        self.assertEqual(tuple(fixture.seed for fixture in resumed.fixtures), original_fixture_seeds)
        self.assertEqual(resumed.fixtures, uninterrupted.fixtures)
        self.assertEqual(resumed.results, uninterrupted.results)
        self.assertEqual(resumed.standings(), uninterrupted.standings())
        self.assertTrue(resumed.complete)

    def test_save_preserves_unstarted_season_without_locking_future_settings(self):
        season = make_season()
        with tempfile.TemporaryDirectory() as directory:
            loaded = load_season(save_season(season, Path(directory) / "season.json"))
            opts = {"action_config": ActionConfig(interval_seconds=90)}
            result = loaded.play_matchday(loaded.matchdays[0], match_options=opts)
        self.assertEqual(len(result), 2)

    def test_rejects_unsupported_version_and_changed_fixture_seed(self):
        season = make_season()
        season.play_fixture(season.fixtures[0].id,
                            match_options={"action_config": ActionConfig(interval_seconds=90)})
        with tempfile.TemporaryDirectory() as directory:
            path = save_season(season, Path(directory) / "season.json")
            original = json.loads(path.read_text(encoding="utf-8"))
            changed = dict(original, version=999)
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unsupported season save version"):
                load_season(path)

            changed = dict(original)
            changed["fixtures"] = [dict(item) for item in original["fixtures"]]
            changed["fixtures"][0]["seed"] += 1
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schedule"):
                load_season(path)

    def test_rejects_result_statistics_that_do_not_reconcile(self):
        season = make_season()
        season.play_fixture(season.fixtures[0].id,
                            match_options={"action_config": ActionConfig(interval_seconds=90)})
        with tempfile.TemporaryDirectory() as directory:
            path = save_season(season, Path(directory) / "season.json")
            data = json.loads(path.read_text(encoding="utf-8"))
            data["results"][0]["home_stats"]["goals"] += 1
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "reconcile"):
                load_season(path)


if __name__ == "__main__":
    unittest.main()
