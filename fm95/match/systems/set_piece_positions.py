"""Penalty and wall setup under the point-player model; no encroachment simulation."""
from fm95.match.spatial.pitch import Location
from fm95.match.systems.restart_positions import EPSILON, clear_distance
from fm95.match.mechanics.set_pieces import goal_centre


def penalty_positions(attackers, defenders, locations, taker_id, ball, direction, pitch):
    result = dict(locations)
    keeper = next(p for p in defenders if p.is_goalkeeper)
    goal = goal_centre(direction)
    result[taker_id],result[keeper.id] = ball,goal
    depth = max(pitch.penalty_depth+EPSILON,
                pitch.distance(ball,goal)+9.15+EPSILON)
    limit = goal.x-int(direction)*depth/pitch.length
    if not 0 <= limit <= 1:
        raise ValueError("Pitch cannot accommodate the penalty setup.")
    for player in attackers+defenders:
        if player.id not in (taker_id,keeper.id):
            point = result[player.id]
            result[player.id] = Location(min(point.x,limit) if int(direction)==1 else max(point.x,limit),point.y)
    return result


def clear_attacking_wall(players, wall, locations, ball, direction, pitch):
    """Keep attackers >=1 m from a wall of at least three defenders.

    Candidate projections are checked against the entire wall, rather than
    pushing an attacker away from one defender into another defender's space.
    The ball is a guaranteed fallback after the wall has been placed legally.
    """
    result = dict(locations)
    if len(wall)<3:
        return result
    points = [locations[p.id] for p in wall]
    for player in players:
        point = result[player.id]
        if all(pitch.distance(point,p)>=1-1e-9 for p in points):
            continue
        candidates = [clear_distance(point,p,1,pitch,-int(direction)) for p in points]+[ball]
        legal = [p for p in candidates if all(pitch.distance(p,w)>=1-1e-9 for w in points)]
        if not legal:
            raise ValueError("The wall must be separated from the kicker before setup.")
        result[player.id] = min(legal,key=lambda p:pitch.distance(point,p))
    return result
