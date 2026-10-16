"""Versioned, validated JSON persistence for completed season fixtures."""

from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from fm95.match.mechanics.actions import ActionConfig
from fm95.match.mechanics.attacking import AttackConfig
from fm95.match.mechanics.boundaries import OutOfPlayConfig
from fm95.match.mechanics.crossing import CrossConfig
from fm95.match.mechanics.defending import DefenseConfig
from fm95.match.mechanics.goalkeeping import KeeperCrossConfig
from fm95.match.mechanics.offside import OffsideConfig
from fm95.match.mechanics.recovery import RecoveryConfig
from fm95.match.mechanics.set_pieces import SetPieceConfig
from fm95.match.mechanics.shooting import ShotConfig
from fm95.match.mechanics.through_balls import ThroughBallConfig
from fm95.match.mechanics.transitions import TransitionConfig
from fm95.match.mechanics.woodwork import WoodworkConfig
from fm95.match.spatial.pitch import Pitch
from fm95.match.statistics import TeamStats
from fm95.match.systems.fatigue import FatigueConfig
from fm95.match.systems.injuries import InjuryConfig
from fm95.match.systems.substitution_policy import AutoSubstitutionConfig
from fm95.match.systems.substitutions import SubstitutionConfig
from fm95.match.systems.timekeeping import AddedTimeConfig
from fm95.match.tactics import TeamTactics
from fm95.players.attributes import Attributes
from fm95.players.decisions import DecisionConfig, DecisionTendencies
from fm95.players.model import Player
from fm95.teams.model import Team
from fm95.competition.season import Fixture, FixtureResult, Season


SAVE_FORMAT = "fm95-season"
SAVE_VERSION = 1

MATCH_OPTION_TYPES = {
    "action_config": ActionConfig,
    "pitch": Pitch,
    "defense_config": DefenseConfig,
    "recovery_config": RecoveryConfig,
    "shot_config": ShotConfig,
    "out_config": OutOfPlayConfig,
    "cross_config": CrossConfig,
    "keeper_cross_config": KeeperCrossConfig,
    "through_ball_config": ThroughBallConfig,
    "offside_config": OffsideConfig,
    "set_piece_config": SetPieceConfig,
    "substitution_config": SubstitutionConfig,
    "fatigue_config": FatigueConfig,
    "auto_substitution_config": AutoSubstitutionConfig,
    "injury_config": InjuryConfig,
    "attack_config": AttackConfig,
    "transition_config": TransitionConfig,
    "added_time_config": AddedTimeConfig,
    "woodwork_config": WoodworkConfig,
    "decision_config": DecisionConfig,
}
CONFIG_TYPES = {value.__name__: value for value in (*MATCH_OPTION_TYPES.values(), TeamTactics)}


def save_season(season: Season, path: str | os.PathLike) -> Path:
    """Atomically save a season between fixtures and return its destination."""
    if not isinstance(season, Season):
        raise TypeError("save_season expects a Season instance.")
    season.validate()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _season_to_data(season)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(payload, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
    return target


def load_season(path: str | os.PathLike) -> Season:
    """Load a save, rejecting unsupported versions and inconsistent references."""
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Season save is not valid JSON: {exc}") from exc
    _require_object(data, {"format", "version", "season", "rules", "teams", "fixtures", "results", "settings"}, "save")
    if data["format"] != SAVE_FORMAT:
        raise ValueError("File is not an FM95 season save.")
    if type(data["version"]) is not int or data["version"] != SAVE_VERSION:
        raise ValueError(f"Unsupported season save version: {data['version']!r}.")

    season_data = _require_object(data["season"], {"name", "seed"}, "season")
    rules = _require_object(data["rules"], {"points_for_win", "points_for_draw", "points_for_loss"}, "rules")
    teams = tuple(_team_from_data(item) for item in _require_list(data["teams"], "teams"))
    fixtures = tuple(_fixture_from_data(item) for item in _require_list(data["fixtures"], "fixtures"))
    results = tuple(_result_from_data(item) for item in _require_list(data["results"], "results"))
    settings = (_settings_from_data(data["settings"], {team.id for team in teams})
                if data["settings"] is not None else None)
    return Season._restore(
        name=season_data["name"], teams=teams, seed=season_data["seed"],
        points_for_win=rules["points_for_win"], points_for_draw=rules["points_for_draw"],
        points_for_loss=rules["points_for_loss"], fixtures=fixtures, results=results,
        run_settings=settings,
    )


def _season_to_data(season: Season) -> dict[str, Any]:
    settings = season._run_settings
    return {
        "format": SAVE_FORMAT,
        "version": SAVE_VERSION,
        "season": {"name": season.name, "seed": season.seed},
        "rules": {
            "points_for_win": season.points_for_win,
            "points_for_draw": season.points_for_draw,
            "points_for_loss": season.points_for_loss,
        },
        "teams": [_team_to_data(team) for team in season.teams],
        "fixtures": [asdict(fixture) for fixture in season.fixtures],
        "results": [_result_to_data(result) for result in season.results],
        "settings": None if settings is None else {
            "match_options": {key: _config_to_data(value) for key, value in sorted(settings["match_options"].items())},
            "tactics": {key: _config_to_data(value) for key, value in sorted(settings["tactics"].items())},
        },
    }


def _team_to_data(team: Team) -> dict[str, Any]:
    return {
        "id": team.id,
        "name": team.name,
        "lineup": [_player_to_data(player) for player in team.lineup],
        "bench": [_player_to_data(player) for player in team.bench],
    }


def _player_to_data(player: Player) -> dict[str, Any]:
    return {
        "id": player.id,
        "name": player.name,
        "is_goalkeeper": player.is_goalkeeper,
        "attributes": asdict(player.attributes),
        "position": player.position.value,
        "decisions": asdict(player.decisions),
    }


def _team_from_data(data: Any) -> Team:
    item = _require_object(data, {"id", "name", "lineup", "bench"}, "team")
    return Team(
        id=item["id"], name=item["name"],
        lineup=tuple(_player_from_data(player) for player in _require_list(item["lineup"], "lineup")),
        bench=tuple(_player_from_data(player) for player in _require_list(item["bench"], "bench")),
    )


def _player_from_data(data: Any) -> Player:
    from fm95.match.spatial.positions import Position

    item = _require_object(data, {"id", "name", "is_goalkeeper", "attributes", "position", "decisions"}, "player")
    attributes = _require_object(item["attributes"], {field.name for field in fields(Attributes)}, "player attributes")
    decisions = _require_object(item["decisions"], {field.name for field in fields(DecisionTendencies)}, "player decisions")
    if type(item["is_goalkeeper"]) is not bool:
        raise ValueError("Player goalkeeper flag must be a boolean.")
    try:
        position = Position(item["position"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Player position is invalid.") from exc
    return Player(
        id=item["id"], name=item["name"], is_goalkeeper=item["is_goalkeeper"],
        attributes=Attributes(**attributes), decisions=DecisionTendencies(**decisions), position=position,
    )


def _fixture_from_data(data: Any) -> Fixture:
    item = _require_object(data, {"id", "matchday", "home_team_id", "away_team_id", "seed"}, "fixture")
    if (any(not isinstance(item[key], str) or not item[key] for key in ("id", "home_team_id", "away_team_id"))
            or type(item["matchday"]) is not int or type(item["seed"]) is not int):
        raise ValueError("Fixture contains an invalid ID, matchday, or seed.")
    return Fixture(**item)


def _result_to_data(result: FixtureResult) -> dict[str, Any]:
    return {
        "fixture_id": result.fixture_id,
        "home_goals": result.home_goals,
        "away_goals": result.away_goals,
        "home_stats": asdict(result.home_stats),
        "away_stats": asdict(result.away_stats),
        "elapsed_seconds": result.elapsed_seconds,
    }


def _result_from_data(data: Any) -> FixtureResult:
    item = _require_object(data, {"fixture_id", "home_goals", "away_goals", "home_stats", "away_stats", "elapsed_seconds"}, "result")
    if (not isinstance(item["fixture_id"], str) or not item["fixture_id"]
            or any(type(item[key]) is not int or item[key] < 0
                   for key in ("home_goals", "away_goals", "elapsed_seconds"))):
        raise ValueError("Result contains an invalid fixture ID, score, or elapsed time.")
    return FixtureResult(
        fixture_id=item["fixture_id"], home_goals=item["home_goals"], away_goals=item["away_goals"],
        home_stats=_stats_from_data(item["home_stats"]), away_stats=_stats_from_data(item["away_stats"]),
        elapsed_seconds=item["elapsed_seconds"],
    )


def _stats_from_data(data: Any) -> TeamStats:
    item = _require_object(data, {field.name for field in fields(TeamStats)}, "team statistics")
    stats = TeamStats(**item)
    for field in fields(stats):
        value = getattr(stats, field.name)
        if field.name == "team_id":
            if not isinstance(value, str) or not value:
                raise ValueError("Statistics team ID must be a non-empty string.")
        elif field.name in {"possession_percentage", "expected_goals", "average_condition", "distance_covered"}:
            if type(value) not in (int, float) or not _finite(value):
                raise ValueError(f"Statistic {field.name} must be a finite number.")
            if value < 0:
                raise ValueError(f"Statistic {field.name} cannot be negative.")
        elif type(value) is not int or value < 0:
            raise ValueError(f"Statistic {field.name} must be a non-negative integer.")
    if stats.possession_percentage > 100 or stats.average_condition > 1:
        raise ValueError("Statistics contain a value outside its valid range.")
    return stats


def _settings_from_data(data: Any, team_ids: set[str]) -> dict:
    item = _require_object(data, {"match_options", "tactics"}, "settings")
    option_data = _require_mapping(item["match_options"], "match options")
    unknown = set(option_data) - MATCH_OPTION_TYPES.keys()
    if unknown:
        raise ValueError(f"Save contains unknown match settings: {sorted(unknown)}")
    options = {}
    for name, config_data in option_data.items():
        config = _config_from_data(config_data)
        if not isinstance(config, MATCH_OPTION_TYPES[name]):
            raise ValueError(f"Match setting {name} has the wrong configuration type.")
        options[name] = config
    tactics_data = _require_mapping(item["tactics"], "team tactics")
    if set(tactics_data) - team_ids:
        raise ValueError("Saved tactics reference an unknown team.")
    tactics = {team_id: _config_from_data(value) for team_id, value in tactics_data.items()}
    if any(not isinstance(value, TeamTactics) for value in tactics.values()):
        raise ValueError("Team tactics have the wrong configuration type.")
    return {"match_options": options, "tactics": tactics}


def _config_to_data(config: Any) -> dict[str, Any]:
    if type(config).__name__ not in CONFIG_TYPES or not is_dataclass(config):
        raise ValueError(f"Unsupported saved setting type: {type(config).__name__}.")
    return {"type": type(config).__name__, "values": asdict(config)}


def _config_from_data(data: Any) -> Any:
    item = _require_object(data, {"type", "values"}, "configuration")
    if not isinstance(item["type"], str):
        raise ValueError("Configuration type must be a string.")
    config_type = CONFIG_TYPES.get(item["type"])
    if config_type is None:
        raise ValueError(f"Unknown saved configuration type: {item['type']!r}.")
    values = _require_object(item["values"], {field.name for field in fields(config_type)}, "configuration values")
    try:
        return config_type(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid saved {config_type.__name__}: {exc}") from exc


def _require_object(value: Any, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label.capitalize()} must be an object.")
    actual = set(value)
    if actual != keys:
        missing, extra = sorted(keys - actual), sorted(actual - keys)
        raise ValueError(f"{label.capitalize()} keys are invalid (missing={missing}, extra={extra}).")
    return value


def _require_list(value: Any, label: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{label.capitalize()} must be a list.")
    return value


def _require_mapping(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label.capitalize()} must be an object.")
    return value


def _finite(value: int | float) -> bool:
    import math
    return math.isfinite(value)
