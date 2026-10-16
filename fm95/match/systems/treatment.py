"""Temporary withdrawal and referee-authorised return state (running-clock protocol)."""
from dataclasses import dataclass
from fm95.match.spatial.positions import Position

@dataclass(frozen=True)
class Treatment:
    team_id: str
    player_id: str
    started_at: int
    position: Position
    eligible_at: int | None = None
    exempt: bool = False
