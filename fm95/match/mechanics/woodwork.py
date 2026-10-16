"""Optional abstract woodwork contacts; probabilities await final calibration."""
from dataclasses import dataclass, replace
from math import isfinite
from fm95.match.spatial.pitch import Location


@dataclass(frozen=True)
class WoodworkConfig:
    enabled: bool = False
    contact_probability: float = .05
    goal_after_contact_probability: float = .1
    rebound_distance: float = 8

    def __post_init__(self):
        if type(self.enabled) is not bool: raise ValueError('Woodwork enabled must be boolean.')
        for name in ('contact_probability','goal_after_contact_probability'):
            value=getattr(self,name)
            if type(value) not in (int,float) or not isfinite(value) or not 0<=value<=1:
                raise ValueError(f'{name} must be in [0,1].')
        if type(self.rebound_distance) not in (int,float) or not isfinite(self.rebound_distance) or self.rebound_distance<0:
            raise ValueError('Woodwork rebound distance must be finite and nonnegative.')


def resolve_contact(result, direction, pitch, rng, config):
    if not config.enabled: return result,None,None
    mass=max(0,1-result.block_probability-result.on_target_probability)*config.contact_probability*config.goal_after_contact_probability
    result=replace(result,goal_probability=result.goal_probability+mass,
                   on_target_probability=result.on_target_probability+mass)
    if result.outcome!='shot_missed' or config.contact_probability==0 or rng.random()>=config.contact_probability:
        return result,None,None
    part=rng.choice(('near_post','far_post','crossbar'))
    side=-1 if part=='near_post' else 1 if part=='far_post' else 0
    point=Location(1 if int(direction)==1 else 0,.5+side*pitch.goal_width/(2*pitch.width))
    goal=config.goal_after_contact_probability>0 and rng.random()<config.goal_after_contact_probability
    return replace(result,outcome='goal' if goal else 'shot_woodwork',intended_on_target=bool(goal)),part,point
