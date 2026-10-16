"""Trace a shot's intent through its immediately represented deflection."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ShotAttribution:
    event_index: int
    team_id: str
    shooter_id: str
    intended_on_target: bool
