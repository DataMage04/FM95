"""Match engine and compatibility exports for match-domain types."""

from importlib import import_module

_ENGINE_EXPORTS = {
    "Discipline", "Match", "MatchEvent", "Phase", "Possession", "Restart", "TeamInPlay",
}


def __getattr__(name):
    if name in ("Player",):
        return import_module("fm95.players.model").Player
    if name == "Team":
        return import_module("fm95.teams.model").Team
    if name in _ENGINE_EXPORTS:
        return getattr(import_module("fm95.match.engine"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["Discipline", "Match", "MatchEvent", "Phase", "Player", "Possession",
           "Restart", "Team", "TeamInPlay"]
