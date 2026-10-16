import json
from pathlib import Path
import tempfile
import unittest

from fm95.competition.manager import Manager, cpu_selection
from fm95.competition.persistence import load_season, save_season
from fm95.competition.season import Season
from fm95.match.mechanics.actions import ActionConfig
from fm95.match.tactics import TeamTactics
from fm95.players.demo import demo_team
from fm95.teams.club import SquadSelection


def make_season():
    return Season("manager-test", [demo_team(f"club-{i}", f"Club {i}", include_bench=True)
                                    for i in range(4)], seed=551)


class ManagerSeasonTests(unittest.TestCase):
    def test_manager_xi_cpu_policy_tactics_and_save_resume(self):
        uninterrupted, interrupted = make_season(), make_season()
        club = interrupted.teams[0]
        xi = tuple(player.id for player in club.squad if player.id != club.lineup[0].id)[:10]
        xi = (club.lineup[0].id, *xi)
        assignment_args = dict(manager=Manager("manager-1", "Alex Coach"), team_id=club.id,
                               selection=SquadSelection(xi),
                               tactics=TeamTactics(pressing=.8, tempo=.65))
        interrupted.assign_manager(**assignment_args)
        uninterrupted.assign_manager(**assignment_args)
        self.assertEqual(cpu_selection(interrupted.teams[1], interrupted.fixtures[0].seed),
                         cpu_selection(interrupted.teams[1], interrupted.fixtures[0].seed))
        opts = {"action_config": ActionConfig(interval_seconds=900)}
        for season in (uninterrupted, interrupted):
            season.play_matchday(season.matchdays[0], match_options=opts)
        managed_fixture = next(fixture for fixture in interrupted.fixtures_for_matchday(interrupted.matchdays[0])
                               if club.id in (fixture.home_team_id, fixture.away_team_id))
        result = interrupted.result_for(managed_fixture.id)
        self.assertEqual(result.home_lineup if managed_fixture.home_team_id == club.id
                         else result.away_lineup, xi)
        with tempfile.TemporaryDirectory() as folder:
            resumed = load_season(save_season(interrupted, Path(folder) / "season.json"))
            self.assertEqual(resumed.manager_assignment, interrupted.manager_assignment)
            self.assertEqual(resumed.results, interrupted.results)
            for day in resumed.matchdays[1:]:
                for fixture in resumed.fixtures_for_matchday(day):
                    override = ({club.id: TeamTactics(width=.9, tempo=.35)}
                                if club.id in (fixture.home_team_id, fixture.away_team_id) else None)
                    resumed.play_fixture(fixture.id, tactics=override)
        for day in uninterrupted.matchdays[1:]:
            for fixture in uninterrupted.fixtures_for_matchday(day):
                override = ({club.id: TeamTactics(width=.9, tempo=.35)}
                            if club.id in (fixture.home_team_id, fixture.away_team_id) else None)
                uninterrupted.play_fixture(fixture.id, tactics=override)
        self.assertEqual(resumed.results, uninterrupted.results)
        self.assertEqual(resumed.standings(), uninterrupted.standings())
        changed = next(result for result in resumed.results
                       if result.home_tactics.width == .9 or result.away_tactics.width == .9)
        self.assertTrue(changed.home_tactics.width == .9 or changed.away_tactics.width == .9)

    def test_selection_rejects_unregistered_players_and_duplicate_players(self):
        season = make_season()
        club = season.teams[0]
        selection = tuple(player.id for player in club.lineup)
        with self.assertRaises(ValueError):
            season.assign_manager(Manager("m", "Manager"), club.id,
                                  selection=SquadSelection((*selection[:-1], "outsider")))
        with self.assertRaises(ValueError):
            SquadSelection((*selection[:-1], selection[0]))

    def test_v1_save_migrates_to_club_rosters(self):
        season = make_season()
        with tempfile.TemporaryDirectory() as folder:
            path = save_season(season, Path(folder) / "season.json")
            data = json.loads(path.read_text())
            data["version"] = 1
            data.pop("manager")
            for club in data["teams"]:
                players = club.pop("players")
                lineup_ids = set(club.pop("default_lineup_ids"))
                club["lineup"] = [player for player in players if player["id"] in lineup_ids]
                club["bench"] = [player for player in players if player["id"] not in lineup_ids]
            path.write_text(json.dumps(data))
            loaded = load_season(path)
        self.assertEqual(loaded.teams, season.teams)


if __name__ == "__main__":
    unittest.main()
