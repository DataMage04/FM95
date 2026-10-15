"""Run the FM95 match demo: python main.py."""

from fm95.match import Match
from fm95.demo import demo_team
from fm95.batch import run_match


def main():
    match = Match(demo_team("home", "Windhoek FC"), demo_team("away", "Coastal FC"), seed=95)
    run_match(match)

    print("First 10 passes/take-ons each, all shots, restarts and match lifecycle events:")
    shown_passes = 0
    shown_dribbles = 0
    for event in match.events:
        is_pass = event.kind.startswith("pass_")
        if event.kind.startswith("dribble_"):
            shown_dribbles += 1
            if shown_dribbles > 10:
                continue
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
        probability = (f" completion_p={event.completion_probability:.3f}"
                       if event.completion_probability is not None else "")
        quality = f" model_xG={event.goal_probability:.3f}" if event.goal_probability is not None else ""
        challenge = (f" defender={event.defender_id}, take_on_p={event.dribble_success_probability:.3f}"
                     if event.defender_id else "")
        foul = f" fouled_player={event.fouled_player_id}" if event.fouled_player_id else ""
        print(f"{minutes:02}:{seconds:02} {event.kind}{team}{ball}{target}{won}{keeper}{probability}{quality}{challenge}{foul}")
    for team in (match.home, match.away):
        stats = match.statistics(team.id)
        print(f"{team.name}: {stats.passes_completed}/{stats.passes_attempted} passes completed; "
              f"{stats.shots} shots, {stats.shots_on_target} on target, {stats.goals} goals; "
              f"{stats.possession_percentage:.1f}% possession; model xG={stats.expected_goals:.2f}; "
              f"take-ons={stats.dribbles_completed}/{stats.dribbles_attempted}; "
              f"tackles={stats.tackles_won}/{stats.tackles_attempted}; fouls={stats.fouls_committed}; "
              f"free kicks taken={stats.free_kicks_taken}")
    print(f"{match.home.name} {match.home_goals}–{match.away_goals} {match.away.name}")
    print("Neutral-attribute demo: values are provisional, restart handling is simplified.")


if __name__ == "__main__":
    main()
