"""Run the FM95 match demo: python main.py."""

from collections import Counter
from fm95.match import Match, Phase, Player, Team


def demo_team(team_id: str, name: str) -> Team:
    return Team(team_id, name, tuple(
        Player(f"{team_id}-{n}", f"{name} Player {n}", is_goalkeeper=n == 1)
        for n in range(1, 12)
    ))


def main():
    match = Match(demo_team("home", "Windhoek FC"), demo_team("away", "Coastal FC"), seed=95)
    match.start()
    while match.phase != Phase.FULL_TIME:
        if match.phase == Phase.HALF_TIME:
            match.resume()
        else:
            match.step()

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
        counts = Counter(e.kind for e in match.events if e.team_id == team.id)
        completed = counts["pass_completed"]
        attempts = completed + counts["pass_intercepted"]
        shots = counts["goal"] + counts["shot_saved"] + counts["shot_missed"]
        on_target = counts["goal"] + counts["shot_saved"]
        print(f"{team.name}: {completed}/{attempts} passes completed; "
              f"{shots} shots, {on_target} on target, {counts['goal']} goals")
    print(f"{match.home.name} {match.home_goals}–{match.away_goals} {match.away.name}")
    print("Equal-player prototype: probabilities are provisional, restarts are instantaneous.")


if __name__ == "__main__":
    main()
