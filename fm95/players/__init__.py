"""Player identity, attributes, tendencies, and squad generation."""

from importlib import import_module

_EXPORTS = {
    "Attributes": ("fm95.players.attributes", "Attributes"),
    "DecisionConfig": ("fm95.players.decisions", "DecisionConfig"),
    "DecisionTendencies": ("fm95.players.decisions", "DecisionTendencies"),
    "Player": ("fm95.players.model", "Player"),
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)


__all__ = list(_EXPORTS)
