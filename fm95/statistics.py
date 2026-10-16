"""Read-only statistics snapshots derived from events and elapsed possession."""

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class TeamStats:
    team_id: str
    goals: int
    passes_attempted: int
    passes_completed: int
    shots: int
    shots_on_target: int
    saves: int
    interceptions: int
    possession_seconds: int
    possession_percentage: float
    expected_goals: float
    dribbles_attempted: int
    dribbles_completed: int
    tackles_attempted: int
    tackles_won: int
    fouls_committed: int
    fouls_suffered: int
    free_kicks_awarded: int
    free_kicks_taken: int
    yellow_cards: int
    red_cards: int
    presses_attempted: int
    presses_won: int
    pressing_fouls: int
    misplaced_passes: int
    recoveries: int
    shots_blocked: int
    blocks: int
    parries: int
    passes_out: int
    throw_ins_awarded: int
    throw_ins_taken: int
    corners_awarded: int
    corners_taken: int
    goal_kicks_awarded: int
    goal_kicks_taken: int
    crosses_attempted: int
    crosses_delivered: int
    aerials_attempted: int
    aerials_won: int
    headed_shots: int
    headed_goals: int
    headed_clearances: int
    keeper_cross_attempts: int
    crosses_claimed: int
    crosses_punched: int
    through_balls_attempted: int
    through_balls_completed: int
    offsides: int
    passes_offside: int
    indirect_free_kicks_awarded: int
    indirect_free_kicks_taken: int
    penalties_awarded: int
    penalties_taken: int
    penalties_scored: int
    penalties_saved: int
    penalties_off_target: int
    direct_free_kick_shots: int
    direct_free_kick_goals: int
    long_passes_attempted: int
    long_passes_completed: int
    tactical_changes: int
    injuries: int
    forced_substitutions: int
    dropped_balls_awarded: int
    dropped_balls_taken: int
    automatic_substitutions: int
    substitutions: int
    substitution_windows: int
    average_condition: float
    distance_covered: float
    player_seconds: int
    keeper_cross_failures: int

    @property
    def pass_completion_percentage(self) -> float:
        return 100 * self.passes_completed / self.passes_attempted if self.passes_attempted else 0.0


def team_statistics(team_id, opponent_id, events, possession_seconds, *, conditions=None, active_ids=()) -> TeamStats:
    conditions = conditions or {}
    own = Counter(e.kind for e in events if e.team_id == team_id)
    opponent = Counter(e.kind for e in events if e.team_id == opponent_id)
    total = sum(possession_seconds.values())
    held = possession_seconds[team_id]
    return TeamStats(
        team_id=team_id, goals=own["goal"],
        passes_attempted=own["pass_completed"] + own["pass_intercepted"] + own["pass_loose"] + own["pass_out"] + own["pass_offside"],
        passes_completed=own["pass_completed"],
        shots=own["goal"] + own["shot_saved"] + own["shot_missed"] + own["shot_blocked"] + own["shot_parried"],
        shots_on_target=own["goal"] + own["shot_saved"] + own["shot_parried"],
        saves=opponent["shot_saved"] + opponent["shot_parried"], interceptions=opponent["pass_intercepted"],
        possession_seconds=held, possession_percentage=100 * held / total if total else 0.0,
        expected_goals=sum(e.goal_probability for e in events
                           if e.team_id == team_id and e.kind in ("goal", "shot_saved", "shot_missed", "shot_blocked", "shot_parried")
                           and e.goal_probability is not None),
        dribbles_attempted=own["dribble_completed"] + own["dribble_tackled"] + own["dribble_dispossessed"],
        dribbles_completed=own["dribble_completed"],
        tackles_attempted=opponent["dribble_completed"] + opponent["dribble_tackled"]
                          + opponent["dribble_dispossessed"] + own["press_won"]
                          + own["press_evaded"] + own["press_dispossessed"],
        tackles_won=opponent["dribble_tackled"] + opponent["dribble_dispossessed"]
                    + own["press_won"] + own["press_dispossessed"],
        fouls_committed=own["foul"], fouls_suffered=opponent["foul"],
        free_kicks_awarded=own["free_kick_awarded"] + own["indirect_free_kick_awarded"],
        free_kicks_taken=own["free_kick_taken"] + own["indirect_free_kick_taken"],
        yellow_cards=own["yellow_card"], red_cards=own["red_card"],
        presses_attempted=own["press_won"] + own["press_evaded"] + own["press_dispossessed"],
        presses_won=own["press_won"] + own["press_dispossessed"], pressing_fouls=own["press_foul"],
        misplaced_passes=own["pass_loose"], recoveries=own["ball_recovered"],
        shots_blocked=own["shot_blocked"], blocks=opponent["shot_blocked"], parries=opponent["shot_parried"],
        passes_out=own["pass_out"], throw_ins_awarded=own["throw_in_awarded"], throw_ins_taken=own["throw_in_taken"],
        corners_awarded=own["corner_awarded"], corners_taken=own["corner_taken"],
        goal_kicks_awarded=own["goal_kick_awarded"], goal_kicks_taken=own["goal_kick_taken"],
        crosses_attempted=own["cross_delivered"] + own["cross_out"] + own["cross_loose"],
        crosses_delivered=own["cross_delivered"],
        aerials_attempted=own["aerial_won"] + opponent["aerial_won"], aerials_won=own["aerial_won"],
        headed_shots=sum(e.team_id == team_id and e.shot_type == "header"
                         and e.kind in ("goal", "shot_saved", "shot_missed", "shot_blocked", "shot_parried") for e in events),
        headed_goals=sum(e.team_id == team_id and e.shot_type == "header" and e.kind == "goal" for e in events),
        headed_clearances=own["headed_clearance"],
        keeper_cross_attempts=own["keeper_cross_claimed"]+own["keeper_cross_punched"]+own["keeper_cross_missed"],
        crosses_claimed=own["keeper_cross_claimed"], crosses_punched=own["keeper_cross_punched"],
        through_balls_attempted=sum(e.team_id == team_id and e.pass_type == "through" for e in events),
        through_balls_completed=sum(e.team_id == team_id and e.pass_type == "through"
                                    and e.kind == "pass_completed" for e in events),
        offsides=own["offside"], passes_offside=own["pass_offside"],
        indirect_free_kicks_awarded=own["indirect_free_kick_awarded"],
        indirect_free_kicks_taken=own["indirect_free_kick_taken"],
        penalties_awarded=own["penalty_awarded"], penalties_taken=own["penalty_taken"],
        penalties_scored=sum(e.team_id == team_id and e.shot_type == "penalty" and e.kind == "goal" for e in events),
        penalties_saved=sum(e.team_id == opponent_id and e.shot_type == "penalty"
                            and e.kind in ("shot_saved", "shot_parried") for e in events),
        penalties_off_target=sum(e.team_id == team_id and e.shot_type == "penalty"
                                 and e.kind == "shot_missed" for e in events),
        direct_free_kick_shots=sum(e.team_id == team_id and e.shot_type == "direct_free_kick" for e in events),
        direct_free_kick_goals=sum(e.team_id == team_id and e.shot_type == "direct_free_kick"
                                   and e.kind == "goal" for e in events),
        long_passes_attempted=sum(e.team_id == team_id and e.pass_type == "long" for e in events),
        long_passes_completed=sum(e.team_id == team_id and e.pass_type == "long" and e.kind == "pass_completed" for e in events),
        tactical_changes=own["tactics_changed"],
        injuries=own["injury"],
        forced_substitutions=sum(e.team_id == team_id and e.kind == "substitution" and e.reason == "injury" for e in events),
        dropped_balls_awarded=own["dropped_ball_awarded"], dropped_balls_taken=own["dropped_ball_taken"],
        automatic_substitutions=sum(e.team_id == team_id and e.kind == "substitution"
                                    and e.automatic for e in events),
        substitutions=own["substitution"], substitution_windows=own["substitution_window"],
        average_condition=(sum(conditions[p].energy for p in active_ids)/len(active_ids) if active_ids else 1.0),
        distance_covered=sum(c.distance_covered for c in conditions.values()),
        player_seconds=sum(c.seconds_played for c in conditions.values()),
        keeper_cross_failures=own["keeper_cross_missed"],
    )
