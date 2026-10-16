"""Administrative restart setup, not simulated walking or encroachment sanctions.

Distances follow IFAB Laws 8, 13, 15, 16 and 17. The point ball sits at the
corner itself, so 10.15 m from that point conservatively clears the 1 m arc.
"""
from math import hypot

from fm95.match.spatial.pitch import Location


EPSILON = 1e-7


def clear_distance(point, ball, distance, pitch, fallback_direction, *, half_direction=None):
    if pitch.distance(point, ball) >= distance-1e-9:
        return point
    dx,dy = (point.x-ball.x)*pitch.length,(point.y-ball.y)*pitch.width
    vectors = [(dx,dy)] if hypot(dx,dy) > 1e-12 else [(int(fallback_direction),0)]
    vectors += [((x-ball.x)*pitch.length,(y-ball.y)*pitch.width)
                for x,y in ((0,0),(0,1),(1,0),(1,1))]
    choices = []
    for vx,vy in vectors:
        length = hypot(vx,vy)
        if not length:
            continue
        target = Location(max(0,min(1,ball.x+vx/length*(distance+EPSILON)/pitch.length)),
                          max(0,min(1,ball.y+vy/length*(distance+EPSILON)/pitch.width)))
        if (pitch.distance(target,ball) >= distance-1e-9
                and (half_direction is None or (target.x-.5)*int(half_direction) >= -1e-12)):
            choices.append(target)
    if not choices:
        raise ValueError("Pitch cannot accommodate the required restart clearance.")
    return min(choices,key=lambda p:pitch.distance(point,p))


def outside_area(point, direction, pitch):
    if not pitch.in_penalty_area(point,direction):
        return point
    x = (pitch.penalty_depth+EPSILON)/pitch.length
    candidates = [Location(x if int(direction)==1 else 1-x,point.y)]
    for y in (.5-(pitch.penalty_width/2+EPSILON)/pitch.width,
              .5+(pitch.penalty_width/2+EPSILON)/pitch.width):
        if 0 <= y <= 1:
            candidates.append(Location(point.x,y))
    return min(candidates,key=lambda p:pitch.distance(point,p))


def restart_positions(kind, attackers, defenders, locations, taker_id, ball, direction, pitch):
    result = dict(locations)
    result[taker_id] = ball
    if kind == 'kickoff':
        for player in attackers:
            if player.id != taker_id:
                p = result[player.id]
                result[player.id] = Location(min(p.x,.5) if int(direction)==1 else max(p.x,.5),p.y)
        for player in defenders:
            p = result[player.id]
            p = Location(max(p.x,.5) if int(direction)==1 else min(p.x,.5),p.y)
            result[player.id] = clear_distance(p,ball,9.15,pitch,direction,half_direction=direction)
    elif kind == 'dropped_ball':
        for player in attackers+defenders:
            if player.id != taker_id:
                result[player.id] = clear_distance(result[player.id],ball,4,pitch,direction)
    elif kind in ('throw_in','corner','free_kick','indirect_free_kick','goal_kick'):
        for player in defenders:
            p = result[player.id]
            if kind == 'goal_kick' or (kind in ('free_kick','indirect_free_kick')
                                      and pitch.in_penalty_area(ball,direction)):
                p = outside_area(p,direction,pitch)
            if kind != 'goal_kick':
                # Free-kick opponents may stand on their goal line between posts.
                own_end = 1 if int(direction)==1 else 0
                goal_line_exception = (kind in ('free_kick','indirect_free_kick')
                    and abs(p.x-own_end)<1e-12 and abs(p.y-.5)*pitch.width <= pitch.goal_width/2)
                if not goal_line_exception:
                    radius = 2 if kind == 'throw_in' else 10.15 if kind == 'corner' else 9.15
                    p = clear_distance(p,ball,radius,pitch,direction)
                    if kind in ('free_kick','indirect_free_kick') and pitch.in_penalty_area(ball,direction):
                        p = outside_area(p,direction,pitch)
            result[player.id] = p
    return result
