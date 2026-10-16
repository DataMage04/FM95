import unittest

from fm95.match.mechanics.actions import ActionConfig
from fm95.players.demo import demo_team
from fm95.match import Match, Phase
from fm95.match.simulation import run_match
from fm95.competition.season import Season


def teams(count):
    return [demo_team(f"club-{i}", f"Club {i}") for i in range(count)]


class SeasonScheduleTests(unittest.TestCase):
    def test_even_league_has_each_home_and_away_pair_once(self):
        season = Season("test", teams(4), seed=17)
        self.assertEqual(len(season.fixtures), 4 * 3)
        self.assertEqual(len(season.matchdays), 6)
        self.assertEqual(len({fixture.seed for fixture in season.fixtures}), len(season.fixtures))
        self.assertEqual([len(season.fixtures_for_matchday(day)) for day in season.matchdays], [2] * 6)
        season.validate()

    def test_odd_league_has_a_bye_each_matchday(self):
        season = Season("odd", teams(5), seed=17)
        self.assertEqual(len(season.fixtures), 5 * 4)
        self.assertEqual(len(season.matchdays), 10)
        for day in season.matchdays:
            fixtures = season.fixtures_for_matchday(day)
            self.assertEqual(len(fixtures), 2)
            self.assertEqual(len({team_id for fixture in fixtures
                                  for team_id in (fixture.home_team_id, fixture.away_team_id)}), 4)

    def test_schedule_and_fixture_seeds_repeat_for_same_seed(self):
        first = Season("same", teams(6), seed=95)
        second = Season("same", teams(6), seed=95)
        self.assertEqual(first.fixtures, second.fixtures)
        different = Season("same", teams(6), seed=96)
        self.assertNotEqual(first.fixtures, different.fixtures)

    def test_rejects_invalid_entries_and_points(self):
        with self.assertRaises(ValueError):
            Season("empty", teams(1), seed=1)
        with self.assertRaises(ValueError):
            Season("bad points", teams(2), seed=1, points_for_win=-1)
        duplicate = [demo_team("x", "X"), demo_team("x", "Other")]
        with self.assertRaises(ValueError):
            Season("duplicate", duplicate, seed=1)


class SeasonExecutionTests(unittest.TestCase):
    def test_result_is_recorded_once_and_table_reconciles(self):
        season = Season("two-club", teams(2), seed=95)
        fixture = season.fixtures[0]
        opts = {"action_config": ActionConfig(interval_seconds=90)}
        result = season.play_fixture(fixture.id, match_options=opts)
        self.assertEqual(season.result_for(fixture.id), result)
        self.assertEqual((result.home_goals, result.away_goals),
                         (result.home_stats.goals, result.away_stats.goals))
        self.assertEqual(sum(row.played for row in season.standings()), 2)
        self.assertEqual(sum(row.points for row in season.standings()),
                         3 if result.home_goals != result.away_goals else 2)
        with self.assertRaises(ValueError):
            season.play_fixture(fixture.id, match_options=opts)
        season.validate()

    def test_matchday_can_resume_after_partial_completion(self):
        season = Season("four-club", teams(4), seed=95)
        day = season.matchdays[0]
        fixtures = season.fixtures_for_matchday(day)
        opts = {"action_config": ActionConfig(interval_seconds=90)}
        season.play_fixture(fixtures[0].id, match_options=opts)
        remaining = season.play_matchday(day, match_options=opts)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(season.play_matchday(day, match_options=opts), ())
        self.assertEqual(len(season.results), 2)

    def test_matchday_order_is_enforced(self):
        season = Season("ordered", teams(4), seed=95)
        with self.assertRaises(ValueError):
            season.play_matchday(2, match_options={"action_config": ActionConfig(interval_seconds=90)})
        later = next(fixture for fixture in season.fixtures if fixture.matchday == 2)
        with self.assertRaises(ValueError):
            season.play_fixture(later.id, match_options={"action_config": ActionConfig(interval_seconds=90)})

    def test_fixture_seed_reproduces_stored_result(self):
        season = Season("replay", teams(2), seed=95)
        fixture = season.fixtures[0]
        home = next(team for team in season.teams if team.id == fixture.home_team_id)
        away = next(team for team in season.teams if team.id == fixture.away_team_id)
        options = {"action_config": ActionConfig(interval_seconds=90)}
        match = run_match(Match(home, away, seed=fixture.seed, **options))
        result = season.play_fixture(fixture.id, match_options=options)
        self.assertEqual(match.phase, Phase.FULL_TIME)
        self.assertEqual((match.home_goals, match.away_goals),
                         (result.home_goals, result.away_goals))
        self.assertEqual(match.events, run_match(Match(home, away, seed=fixture.seed, **options)).events)


if __name__ == "__main__":
    unittest.main()
