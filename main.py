"""Run the FM95 match demo: python main.py."""

from fm95.match import Match
from fm95.players.demo import demo_team
from fm95.match.simulation import run_match
from fm95.match.tactics import preset
from fm95.match.systems.injuries import InjuryConfig
from fm95.match.systems.substitution_policy import AutoSubstitutionConfig


def halftime_changes(match):
    """Example manual management callback for matches with automatic control disabled."""
    for team in (match.home, match.away):
        outgoing = [p for p in match.active_players(team.id) if not p.is_goalkeeper][-2:]
        incoming = [p for p in match.available_substitutes(team.id) if not p.is_goalkeeper][:2]
        match.substitute_many(team.id, tuple((old.id, new.id) for old, new in zip(outgoing, incoming)))


def main():
    match = Match(demo_team("home", "Windhoek FC", include_bench=True),
                  demo_team("away", "Coastal FC", include_bench=True), seed=95,
                  auto_substitution_config=AutoSubstitutionConfig(enabled=True), injury_config=InjuryConfig(enabled=True),
                  home_tactics=preset("pressing"), away_tactics=preset("possession"))
    run_match(match)

    print("Provisional tactics: Windhoek FC pressing; Coastal FC possession.")
    print("First 10 passes/take-ons each, all shots, restarts and match lifecycle events:")
    shown_passes = 0
    shown_dribbles = 0
    shown_presses = 0
    shown_loose = 0
    shown_aerial = 0
    for event in match.events:
        is_pass = event.kind.startswith("pass_")
        if event.kind.startswith("cross_") or event.kind in ("aerial_won", "headed_clearance"):
            shown_aerial += 1
            if shown_aerial > 20:
                continue
        if event.kind in ("ball_loose", "ball_recovered", "ball_unrecovered"):
            shown_loose += 1
            if shown_loose > 10:
                continue
        if event.kind.startswith("press_"):
            shown_presses += 1
            if shown_presses > 10:
                continue
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
        pressure = (f" pressure={event.pressure:.2f} defender={event.pressing_player_id}"
                    if event.pressing_player_id else "")
        opponent = f" opponent={event.opponent_player_id}" if event.opponent_player_id else ""
        block = f" blocker={event.blocking_player_id} block_p={event.block_probability:.3f}" if event.blocking_player_id else ""
        header = f" shot_type={event.shot_type}" if event.shot_type else ""
        substitution = (f" off={event.outgoing_player_id} on={event.incoming_player_id} reason={event.reason}"
                        if event.kind == "substitution" else "")
        coordinates = ""
        if event.location is not None:
            x, y = match.pitch.metres(event.location)
            coordinates = f" xy=({x:.1f}, {y:.1f})m"
        print(f"{minutes:02}:{seconds:02} {event.kind}{team}{ball}{coordinates}{target}{won}{keeper}{probability}{quality}{challenge}{foul}{pressure}{opponent}{block}{header}{substitution}")
    for team in (match.home, match.away):
        stats = match.statistics(team.id)
        print(f"{team.name}: {stats.passes_completed}/{stats.passes_attempted} passes completed; "
              f"{stats.shots} shots, {stats.shots_on_target} on target, {stats.goals} goals; "
              f"{stats.possession_percentage:.1f}% possession; model xG={stats.expected_goals:.2f}; "
              f"take-ons={stats.dribbles_completed}/{stats.dribbles_attempted}; "
              f"tackles={stats.tackles_won}/{stats.tackles_attempted}; fouls={stats.fouls_committed}; "
              f"free kicks taken={stats.free_kicks_taken}; "
              f"cards={stats.yellow_cards}Y/{stats.red_cards}R; "
              f"presses won={stats.presses_won}/{stats.presses_attempted}; recoveries={stats.recoveries}; "
              f"blocks={stats.blocks}; parries={stats.parries}; "
              f"throw-ins={stats.throw_ins_taken}; corners={stats.corners_taken}; "
              f"crosses={stats.crosses_delivered}/{stats.crosses_attempted}; "
              f"aerials={stats.aerials_won}/{stats.aerials_attempted}; headed shots={stats.headed_shots}; "
              f"keeper claims={stats.crosses_claimed}; punches={stats.crosses_punched}; offsides={stats.offsides}; "
              f"through balls={stats.through_balls_completed}/{stats.through_balls_attempted}; "
              f"penalties={stats.penalties_scored}/{stats.penalties_taken}; "
              f"direct free-kick shots={stats.direct_free_kick_shots}; "
              f"substitutions={stats.substitutions} ({stats.automatic_substitutions} automatic, "
              f"{stats.substitution_windows} in-play windows); injuries={stats.injuries}; "
              f"condition={100*stats.average_condition:.1f}%; tracked running={stats.distance_covered:.0f}m; "
              f"long passes={stats.long_passes_completed}/{stats.long_passes_attempted}")
    print(f"Uncontrolled ball time: {match.loose_ball_seconds} s; possession shares use controlled time.")
    print(f"Dead-ball restart time: {match.dead_ball_seconds} s")
    print(f"{match.home.name} {match.home_goals}–{match.away_goals} {match.away.name}")
    print(f"Match status: {match.phase.value}")
    print("Neutral-attribute demo: values are provisional, restart handling is simplified.")


if __name__ == "__main__":
    main()
