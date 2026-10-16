"""Explicit represented incidents and deterministic referee decisions.

No random offence frequencies are invented here. Penalty impact is supplied by
an incident observer, not inferred from mere encroachment (IFAB Laws 12–17).
"""
from dataclasses import dataclass
from enum import Enum

class PenaltyOffence(str,Enum):
    ACCIDENTAL_DOUBLE_TOUCH='accidental_double_touch'
    ATTACKER_ENCROACHMENT='attacker_encroachment'
    DEFENDER_ENCROACHMENT='defender_encroachment'
    BOTH_ENCROACHMENT='both_encroachment'
    GOALKEEPER_OFF_LINE='goalkeeper_off_line'
    BACKWARDS='backwards'
    ILLEGAL_FEINT='illegal_feint'
    WRONG_KICKER='wrong_kicker'
    KICKER_AND_KEEPER='kicker_and_keeper'

@dataclass(frozen=True)
class PenaltyIncident:
    offence: PenaltyOffence
    player_id: str | None = None
    impact: bool = True
    def __post_init__(self):
        if not isinstance(self.offence,PenaltyOffence) or type(self.impact) is not bool:
            raise ValueError('Penalty incident requires an offence enum and boolean impact.')
        if self.player_id is not None and (not isinstance(self.player_id,str) or not self.player_id):
            raise ValueError('Offender ID must be a nonempty string.')


def penalty_decision(incident,outcome):
    if incident is None:return 'allow'
    offence=incident.offence
    scored=outcome=='goal'
    if offence in (PenaltyOffence.BACKWARDS,PenaltyOffence.ILLEGAL_FEINT,
                   PenaltyOffence.WRONG_KICKER,PenaltyOffence.KICKER_AND_KEEPER):return 'indirect'
    if offence==PenaltyOffence.ACCIDENTAL_DOUBLE_TOUCH:return 'retake' if scored else 'indirect'
    if offence==PenaltyOffence.GOALKEEPER_OFF_LINE:
        return 'retake' if not scored and (outcome in ('shot_saved','shot_parried') or incident.impact) else 'allow'
    if not incident.impact:return 'allow'
    if offence==PenaltyOffence.BOTH_ENCROACHMENT:return 'retake'
    if offence==PenaltyOffence.ATTACKER_ENCROACHMENT:return 'retake' if scored else 'indirect'
    return 'allow' if scored else 'retake'

class TouchKind(str,Enum):
    CONTACT='contact'
    KICK='deliberate_kick'
    THROW='throw_in'
    HEADER='header'
    HAND='hand'

@dataclass(frozen=True)
class BallTouch:
    team_id: str
    player_id: str
    kind: TouchKind
    recipient_id: str | None = None
