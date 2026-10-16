"""Goal-mouth detection for the engine's point-ball, ground-plane model.

No height or post collisions are represented. A point exactly on a post's
horizontal coordinate is not treated as a goal. Direct restart restrictions
belong to restart handling, not this geometric test.
"""
from fm95.boundaries import Boundary


def crosses_goal_mouth(exit, pitch):
    return (exit.boundary in (Boundary.LEFT, Boundary.RIGHT)
            and (.5-pitch.goal_width/(2*pitch.width) < exit.location.y
                 < .5+pitch.goal_width/(2*pitch.width)))
