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

    @property
    def pass_completion_percentage(self) -> float:
        return 100 * self.passes_completed / self.passes_attempted if self.passes_attempted else 0.0


def team_statistics(team_id, opponent_id, events, possession_seconds) -> TeamStats:
    own = Counter(e.kind for e in events if e.team_id == team_id)
    opponent = Counter(e.kind for e in events if e.team_id == opponent_id)
    total = sum(possession_seconds.values())
    held = possession_seconds[team_id]
    return TeamStats(
        team_id=team_id, goals=own["goal"],
        passes_attempted=own["pass_completed"] + own["pass_intercepted"] + own["pass_loose"] + own["pass_out"],
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
        free_kicks_awarded=own["free_kick_awarded"], free_kicks_taken=own["free_kick_taken"],
        yellow_cards=own["yellow_card"], red_cards=own["red_card"],
        presses_attempted=own["press_won"] + own["press_evaded"] + own["press_dispossessed"],
        presses_won=own["press_won"] + own["press_dispossessed"], pressing_fouls=own["press_foul"],
        misplaced_passes=own["pass_loose"], recoveries=own["ball_recovered"],
        shots_blocked=own["shot_blocked"], blocks=opponent["shot_blocked"], parries=opponent["shot_parried"],
        passes_out=own["pass_out"], throw_ins_awarded=own["throw_in_awarded"], throw_ins_taken=own["throw_in_taken"],
        corners_awarded=own["corner_awarded"], corners_taken=own["corner_taken"],
        goal_kicks_awarded=own["goal_kick_awarded"], goal_kicks_taken=own["goal_kick_taken"],
    )
