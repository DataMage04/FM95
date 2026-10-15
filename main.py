"""Run the FM95 match demo: python main.py."""

from fm95.match import Match
from fm95.demo import demo_team
from fm95.batch import run_match


def main():
    match = Match(demo_team("home", "Windhoek FC"), demo_team("away", "Coastal FC"), seed=95)
    run_match(match)

    print("First 10 passes, all shots, restarts and match lifecycle events:")
    shown_passes = 0
    for event in match.events:
        is_pass = event.kind.startswith("pass_")
        if is_pass:
            shown_passes += 1
            if shown_passes > 10:
                continue
        minutes, seconds = divmod(event.elapsed_seconds, 60)
        team = f" ({event.team_id})" if event.team_id else ""
        ball = (f" player={event.player_id}, zone=({event.zone.column}, {event.zone.lane})"
                if event.zone is not None else "")
        target = f" receiver={event.receiver_id}" if is_pass else ""
        won = f" interceptor={event.interceptor_id}" if event.interceptor_id else ""
        keeper = f" goalkeeper={event.goalkeeper_id}" if event.goalkeeper_id else ""
        print(f"{minutes:02}:{seconds:02} {event.kind}{team}{ball}{target}{won}{keeper}")
    for team in (match.home, match.away):
        stats = match.statistics(team.id)
        print(f"{team.name}: {stats.passes_completed}/{stats.passes_attempted} passes completed; "
              f"{stats.shots} shots, {stats.shots_on_target} on target, {stats.goals} goals; "
              f"{stats.possession_percentage:.1f}% possession")
    print(f"{match.home.name} {match.home_goals}–{match.away_goals} {match.away.name}")
    print("Equal-player prototype: probabilities are provisional, restarts are instantaneous.")


if __name__ == "__main__":
    main()
