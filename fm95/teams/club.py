"""Persistent club identity and registered roster, separate from fixture teams."""

from dataclasses import dataclass

from fm95.players.model import Player
from fm95.teams.model import Team


@dataclass(frozen=True)
class SquadSelection:
    """Starting XI player IDs. The remaining registered players form the bench."""

    starting_xi: tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, "starting_xi", tuple(self.starting_xi))
        if (len(self.starting_xi) != 11 or any(not isinstance(pid, str) or not pid.strip()
                                               for pid in self.starting_xi)
                or len(set(self.starting_xi)) != 11):
            raise ValueError("A squad selection must contain 11 unique player IDs.")


@dataclass(frozen=True)
class Club:
    id: str
    name: str
    players: tuple[Player, ...]
    default_lineup_ids: tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, "players", tuple(self.players))
        object.__setattr__(self, "default_lineup_ids", tuple(self.default_lineup_ids))
        if not isinstance(self.id, str) or not self.id.strip() or not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Club needs a non-empty ID and name.")
        if len(self.players) < 11 or any(not isinstance(player, Player) for player in self.players):
            raise ValueError("A club must register at least 11 Player instances.")
        ids = [player.id for player in self.players]
        if any(not isinstance(pid, str) or not pid.strip() for pid in ids):
            raise ValueError("Registered players need non-empty string IDs.")
        if len(set(ids)) != len(ids):
            raise ValueError("Registered players must have unique IDs.")
        if len(self.default_lineup_ids) != 11 or len(set(self.default_lineup_ids)) != 11:
            raise ValueError("Club default lineup must contain 11 unique player IDs.")
        if not set(self.default_lineup_ids) <= set(ids):
            raise ValueError("Club default lineup references an unregistered player.")
        selected = [player for player in self.players if player.id in self.default_lineup_ids]
        if sum(player.is_goalkeeper for player in selected) != 1:
            raise ValueError("Club default lineup must contain one goalkeeper.")

    @classmethod
    def from_team(cls, team: Team) -> "Club":
        return cls(team.id, team.name, team.squad, tuple(player.id for player in team.lineup))

    @property
    def squad(self) -> tuple[Player, ...]:
        return self.players

    @property
    def lineup(self) -> tuple[Player, ...]:
        """Compatibility view for existing callers; fixtures use ``to_team``."""
        return tuple(self._by_id[pid] for pid in self.default_lineup_ids)

    @property
    def bench(self) -> tuple[Player, ...]:
        selected = set(self.default_lineup_ids)
        return tuple(player for player in self.players if player.id not in selected)

    @property
    def _by_id(self) -> dict[str, Player]:
        return {player.id: player for player in self.players}

    def to_team(self, selection: SquadSelection | None = None) -> Team:
        selection = selection or SquadSelection(self.default_lineup_ids)
        if not isinstance(selection, SquadSelection):
            raise ValueError("Selection must be a SquadSelection instance.")
        by_id = self._by_id
        if not set(selection.starting_xi) <= by_id.keys():
            raise ValueError(f"Selection for {self.id} references an unregistered player.")
        starters = tuple(by_id[pid] for pid in selection.starting_xi)
        if sum(player.is_goalkeeper for player in starters) != 1:
            raise ValueError("Selected starting XI must contain exactly one goalkeeper.")
        selected = set(selection.starting_xi)
        return Team(self.id, self.name, starters,
                    tuple(player for player in self.players if player.id not in selected))
