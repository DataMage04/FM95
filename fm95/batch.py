"""Run reproducible synthetic matches: python -m fm95.batch --matches 200."""

import argparse
from collections import Counter
from dataclasses import asdict, replace
import json
from typing import Callable

from fm95.woodwork import WoodworkConfig
from fm95.timekeeping import AddedTimeConfig
from fm95.transitions import TransitionConfig
from fm95.attacking import AttackConfig
from fm95.actions import ActionConfig
from fm95.defending import DefenseConfig
from fm95.recovery import RecoveryConfig
from fm95.shooting import ShotConfig
from fm95.boundaries import OutOfPlayConfig
from fm95.crossing import CrossConfig
from fm95.tactics import TeamTactics, preset
from fm95.injuries import InjuryConfig
from fm95.fatigue import FatigueConfig
from fm95.substitution_policy import AutoSubstitutionConfig
from fm95.substitutions import SubstitutionConfig
from fm95.set_pieces import SetPieceConfig
from fm95.offside import OffsideConfig
from fm95.through_balls import ThroughBallConfig
from fm95.goalkeeping import KeeperCrossConfig
from fm95.demo import demo_team
from fm95.match import Match, Phase


def run_match(match: Match, *, on_half_time: Callable[[Match], None] | None = None) -> Match:
    """Run a fresh match to full time, with an optional halftime management callback."""
    match.start()
    while match.phase not in (Phase.FULL_TIME, Phase.ABANDONED):
        if match.phase == Phase.HALF_TIME:
            if on_half_time is not None:
                on_half_time(match)
            match.resume()
        else:
            match.step()
    return match


def run_batch(matches: int = 200, seed: int = 95,
              config: ActionConfig | None = None, defense_config: DefenseConfig | None = None,
              recovery_config: RecoveryConfig | None = None,
              shot_config: ShotConfig | None = None, out_config: OutOfPlayConfig | None = None,
              cross_config: CrossConfig | None = None,
              keeper_cross_config: KeeperCrossConfig | None = None,
              through_ball_config: ThroughBallConfig | None = None,
              offside_config: OffsideConfig | None = None,
              set_piece_config: SetPieceConfig | None = None,
              substitution_config: SubstitutionConfig | None = None,
              fatigue_config: FatigueConfig | None = None,
              auto_substitution_config: AutoSubstitutionConfig | None = None,
              injury_config: InjuryConfig | None = None,
              home_tactics: TeamTactics | None = None, away_tactics: TeamTactics | None = None,
              attack_config: AttackConfig | None = None,
              transition_config: TransitionConfig | None = None,
              added_time_config: AddedTimeConfig | None = None,
              woodwork_config: WoodworkConfig | None = None) -> dict:
    """Match i uses seed+i; retain aggregates only, not every match's event log."""
    if type(matches) is not int or matches < 1:
        raise ValueError("Match count must be a positive integer.")
    if type(seed) is not int:
        raise ValueError("Base seed must be an integer.")
    woodwork_config = woodwork_config if woodwork_config is not None else WoodworkConfig()
    added_time_config = added_time_config if added_time_config is not None else AddedTimeConfig()
    transition_config = transition_config if transition_config is not None else TransitionConfig()
    attack_config = attack_config if attack_config is not None else AttackConfig()
    config = config if config is not None else ActionConfig()
    defense_config = defense_config if defense_config is not None else DefenseConfig()
    recovery_config = recovery_config if recovery_config is not None else RecoveryConfig()
    shot_config = shot_config if shot_config is not None else ShotConfig()
    out_config = out_config if out_config is not None else OutOfPlayConfig()
    cross_config = cross_config if cross_config is not None else CrossConfig()
    keeper_cross_config = keeper_cross_config if keeper_cross_config is not None else KeeperCrossConfig()
    through_ball_config = through_ball_config if through_ball_config is not None else ThroughBallConfig()
    offside_config = offside_config if offside_config is not None else OffsideConfig()
    set_piece_config = set_piece_config if set_piece_config is not None else SetPieceConfig()
    substitution_config = substitution_config if substitution_config is not None else SubstitutionConfig()
    fatigue_config = fatigue_config if fatigue_config is not None else FatigueConfig()
    auto_substitution_config = auto_substitution_config if auto_substitution_config is not None else AutoSubstitutionConfig()
    injury_config = injury_config if injury_config is not None else InjuryConfig()
    home_tactics = home_tactics if home_tactics is not None else TeamTactics()
    away_tactics = away_tactics if away_tactics is not None else TeamTactics()
    teams = (demo_team("home", "Home", include_bench=auto_substitution_config.enabled or injury_config.enabled),
             demo_team("away", "Away", include_bench=auto_substitution_config.enabled or injury_config.enabled))
    initial = Match(*teams)
    totals = {team.id: Counter({key: 0 for key in asdict(initial.statistics(team.id))
                               if key != "team_id"}) for team in teams}
    outcomes, scorelines = Counter(), Counter()
    completed = 0
    loose_seconds = 0
    dead_seconds = 0
    elapsed_seconds = 0
    for index in range(matches):
        match = run_match(Match(*teams, seed=seed + index, action_config=config,
                                defense_config=defense_config, recovery_config=recovery_config,
                                shot_config=shot_config, out_config=out_config, cross_config=cross_config,
                                keeper_cross_config=keeper_cross_config, through_ball_config=through_ball_config,
                                offside_config=offside_config, set_piece_config=set_piece_config,
                                substitution_config=substitution_config, fatigue_config=fatigue_config,
                                auto_substitution_config=auto_substitution_config, injury_config=injury_config,
                                home_tactics=home_tactics, away_tactics=away_tactics, attack_config=attack_config,
                                transition_config=transition_config, added_time_config=added_time_config,woodwork_config=woodwork_config))
        if match.phase == Phase.ABANDONED:
            outcomes["abandoned"] += 1
            continue
        completed += 1
        elapsed_seconds += match.elapsed_seconds
        loose_seconds += match.loose_ball_seconds
        dead_seconds += match.dead_ball_seconds
        for team in teams:
            values = asdict(match.statistics(team.id))
            values.pop("team_id")
            totals[team.id].update(values)
        home_goals, away_goals = match.home_goals, match.away_goals
        outcomes["home_win" if home_goals > away_goals else
                 "away_win" if away_goals > home_goals else "draw"] += 1
        scorelines[f"{home_goals}-{away_goals}"] += 1
    averages = {}
    for team_id, total in totals.items():
        averages[team_id] = {key: value / completed if completed else 0.0
                             for key, value in total.items()}
        averages[team_id]["pass_completion_percentage"] = (
            100 * total["passes_completed"] / total["passes_attempted"]
            if total["passes_attempted"] else 0.0
        )
    return {
        "matches": matches, "completed_matches": completed,
        "base_seed": seed, "configuration": asdict(config),
        "woodwork_configuration": asdict(woodwork_config),
        "added_time_configuration": asdict(added_time_config),
        "average_elapsed_seconds": elapsed_seconds/completed if completed else 0.0,
        "average_added_time_seconds": elapsed_seconds/completed-5400 if completed else 0.0,
        "transition_configuration": asdict(transition_config),
        "attacking_configuration": asdict(attack_config),
        "defense_configuration": asdict(defense_config),
        "recovery_configuration": asdict(recovery_config),
        "shot_configuration": asdict(shot_config),
        "out_of_play_configuration": asdict(out_config),
        "crossing_configuration": asdict(cross_config),
        "home_tactics": asdict(home_tactics), "away_tactics": asdict(away_tactics),
        "injury_configuration": asdict(injury_config),
        "automatic_substitution_configuration": asdict(auto_substitution_config),
        "fatigue_configuration": asdict(fatigue_config),
        "substitution_configuration": asdict(substitution_config),
        "set_piece_configuration": asdict(set_piece_config),
        "offside_configuration": asdict(offside_config),
        "through_ball_configuration": asdict(through_ball_config),
        "keeper_crossing_configuration": asdict(keeper_cross_config),
        "average_dead_ball_seconds": dead_seconds/completed if completed else 0.0,
        "average_loose_ball_seconds": loose_seconds/completed if completed else 0.0,
        "outcomes": {key: outcomes[key] for key in ("home_win", "draw", "away_win", "abandoned")},
        "average_total_goals": averages["home"]["goals"] + averages["away"]["goals"],
        "team_averages": averages, "scorelines": dict(sorted(scorelines.items())),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", type=int, default=200)
    parser.add_argument("--seed", type=int, default=95)
    parser.add_argument("--profile", choices=("prototype", "pl2015"), default="prototype",
                        help="Use the locally fitted StatsBomb PL 2015/16 aggregate research profile")
    parser.add_argument("--context-strength", type=float, default=None,
                        help="Situational effects from 0 (neutral) to 1 (default)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary")
    parser.add_argument("--no-attacking-movement", action="store_true", help="Use static attacking shape targets")
    parser.add_argument("--temporary-injuries", action="store_true", help="Mix temporary treatment into generated injuries (provisional 50 percent)")
    parser.add_argument("--off-ball-offside", action="store_true", help="Enable geometric keeper-screening checks")
    parser.add_argument("--woodwork", action="store_true", help="Enable abstract post/crossbar contacts")
    parser.add_argument("--added-time", action="store_true", help="Represent stoppage delays and per-half added time")
    parser.add_argument("--no-transitions", action="store_true", help="Disable turnover movement responses")
    parser.add_argument("--no-defensive-cover", action="store_true", help="Disable coordinated cover behind the presser")
    parser.add_argument("--no-defense", action="store_true", help="Disable spatial defense for isolation")
    parser.add_argument("--no-loose-balls", action="store_true", help="Disable pass/tackle loose outcomes")
    parser.add_argument("--no-shot-interactions", action="store_true", help="Disable blocks and parries")
    parser.add_argument("--no-out-of-play", action="store_true", help="Disable spatial out-of-play outcomes")
    parser.add_argument("--no-crossing", action="store_true", help="Disable open-play and corner crosses")
    parser.add_argument("--no-keeper-crosses", action="store_true", help="Disable keeper intervention on crosses")
    parser.add_argument("--no-through-balls", action="store_true", help="Disable forward runs and through balls")
    parser.add_argument("--no-offside", action="store_true", help="Disable offside decisions for isolation")
    parser.add_argument("--no-set-pieces", action="store_true", help="Use legacy short free kicks for all fouls")
    parser.add_argument("--no-fatigue", action="store_true", help="Disable condition depletion and performance effects")
    parser.add_argument("--auto-substitutions", action="store_true", help="Enable fatigue management with named benches")
    parser.add_argument("--injuries", action="store_true", help="Enable provisional open-play and foul injuries")
    styles = ("balanced", "pressing", "possession", "direct")
    parser.add_argument("--home-style", choices=styles, default="balanced")
    parser.add_argument("--away-style", choices=styles, default="balanced")
    args = parser.parse_args()
    if args.matches < 1:
        parser.error("--matches must be positive")
    if args.context_strength is not None and not 0 <= args.context_strength <= 1:
        parser.error("--context-strength must be between 0 and 1")
    from fm95.calibration import load_profile, profile_configs
    fitted = args.profile == "pl2015"
    base = profile_configs(load_profile() if fitted else {})
    actions = base["action_config"]
    if args.context_strength is not None:
        actions = replace(actions, context_strength=args.context_strength)
    summary = run_batch(args.matches, args.seed, actions,
                        replace(base["defense_config"], enabled=not args.no_defense, cover_enabled=not args.no_defensive_cover),
                        RecoveryConfig(enabled=not args.no_loose_balls),
                        replace(base["shot_config"], enabled=not args.no_shot_interactions),
                        replace(base["out_config"], enabled=not args.no_out_of_play),
                        replace(base["cross_config"], enabled=not args.no_crossing),
                        KeeperCrossConfig(enabled=not args.no_keeper_crosses),
                        ThroughBallConfig(enabled=not args.no_through_balls),
                        OffsideConfig(enabled=not args.no_offside,screening_enabled=args.off_ball_offside),
                        replace(base["set_piece_config"], enabled=not args.no_set_pieces),
                        fatigue_config=FatigueConfig(enabled=not args.no_fatigue),
                        auto_substitution_config=AutoSubstitutionConfig(enabled=args.auto_substitutions or fitted),
                        injury_config=InjuryConfig(enabled=args.injuries or args.temporary_injuries,temporary_probability=.5 if args.temporary_injuries else 0),
                        home_tactics=preset(args.home_style), away_tactics=preset(args.away_style),
                        attack_config=AttackConfig(enabled=not args.no_attacking_movement),
                        transition_config=TransitionConfig(enabled=not args.no_transitions),
                        added_time_config=AddedTimeConfig(enabled=args.added_time or fitted),woodwork_config=WoodworkConfig(enabled=args.woodwork or fitted))
    summary["calibration_profile"] = args.profile
    if args.json:
        print(json.dumps(summary, indent=2))
        return
    print(f"{args.matches} matches; seeds {args.seed}–{args.seed + args.matches - 1}")
    print(f"Tactics: home={args.home_style}; away={args.away_style} (provisional presets)")
    print(f"Outcomes: {summary['outcomes']}")
    print(f"Mean total goals: {summary['average_total_goals']:.2f}")
    print(f"Mean uncontrolled time: {summary['average_loose_ball_seconds']:.1f} s")
    print(f"Mean elapsed match time: {summary['average_elapsed_seconds']:.1f} s")
    print(f"Mean dead-ball restart time: {summary['average_dead_ball_seconds']:.1f} s")
    for side, stats in summary["team_averages"].items():
        print(f"{side}: goals={stats['goals']:.2f}, model xG={stats['expected_goals']:.2f}, "
              f"shots={stats['shots']:.2f}, "
              f"on target={stats['shots_on_target']:.2f}, "
              f"passes={stats['passes_attempted']:.2f}, "
              f"completion={stats['pass_completion_percentage']:.1f}%, "
              f"possession={stats['possession_percentage']:.1f}%, "
              f"take-ons={stats['dribbles_attempted']:.2f}, tackles won={stats['tackles_won']:.2f}, "
              f"fouls={stats['fouls_committed']:.2f}, "
              f"cards={stats['yellow_cards']:.2f}Y/{stats['red_cards']:.2f}R, "
              f"presses won={stats['presses_won']:.2f}/{stats['presses_attempted']:.2f}, "
              f"recoveries={stats['recoveries']:.2f}, blocks={stats['blocks']:.2f}, "
              f"parries={stats['parries']:.2f}, throws={stats['throw_ins_taken']:.2f}, "
              f"corners={stats['corners_taken']:.2f}, crosses={stats['crosses_attempted']:.2f}, "
              f"headed shots={stats['headed_shots']:.2f}, "
              f"keeper claims={stats['crosses_claimed']:.2f}, punches={stats['crosses_punched']:.2f}, "
              f"offsides={stats['offsides']:.2f}, penalties={stats['penalties_scored']:.2f}/{stats['penalties_taken']:.2f}, "
              f"direct free-kick shots={stats['direct_free_kick_shots']:.2f}, "
              f"condition={100*stats['average_condition']:.1f}%, "
              f"automatic substitutions={stats['automatic_substitutions']:.2f}, "
              f"injuries={stats['injuries']:.2f}")
    print(f"Averages and scorelines cover {summary['completed_matches']} completed matches.")
    print("Synthetic teams; aggregate research calibration only." if fitted else
          "Synthetic baseline; probabilities are uncalibrated. Use --json for all metrics.")


if __name__ == "__main__":
    main()
