"""Run the FM95 match lifecycle demo: python main.py."""

from fm95.match import Match, Phase, Player, Team


def demo_team(team_id: str, name: str) -> Team:
    return Team(team_id, name, tuple(
        Player(f"{team_id}-{n}", f"{name} Player {n}", is_goalkeeper=n == 1)
        for n in range(1, 12)
    ))


def main():
    match = Match(demo_team("home", "Windhoek FC"), demo_team("away", "Coastal FC"))
    match.start()
    while match.phase != Phase.FULL_TIME:
        if match.phase == Phase.HALF_TIME:
            match.resume()
        else:
            match.step()

    for event in match.events:
        minutes, seconds = divmod(event.elapsed_seconds, 60)
        team = f" ({event.team_id})" if event.team_id else ""
        ball = (f" carrier={event.player_id}, zone=({event.zone.column}, {event.zone.lane})"
                if event.zone is not None else "")
        print(f"{minutes:02}:{seconds:02} {event.kind}{team}{ball}")
    print(f"{match.home.name} {match.home_goals}–{match.away_goals} {match.away.name}")
    print("Lifecycle demo only: football actions are not implemented yet.")


if __name__ == "__main__":
    main()
