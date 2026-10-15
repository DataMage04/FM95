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
        passes_attempted=own["pass_completed"] + own["pass_intercepted"],
        passes_completed=own["pass_completed"],
        shots=own["goal"] + own["shot_saved"] + own["shot_missed"],
        shots_on_target=own["goal"] + own["shot_saved"],
        saves=opponent["shot_saved"], interceptions=opponent["pass_intercepted"],
        possession_seconds=held, possession_percentage=100 * held / total if total else 0.0,
        expected_goals=sum(e.goal_probability for e in events
                           if e.team_id == team_id and e.kind in ("goal", "shot_saved", "shot_missed")
                           and e.goal_probability is not None),
    )
