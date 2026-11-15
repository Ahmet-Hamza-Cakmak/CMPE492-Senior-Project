"""Wall outlines around the union of connected corridors."""

from functools import lru_cache
import math

from shapely.geometry import LineString


WALL_HEIGHT = 0.3
WALL_THICKNESS = 0.02


@lru_cache(maxsize=32)
def wall_segments(scenario):
    """Return wall center segments, leaving both route endpoints open.

    Buffering the whole route avoids internal barriers at bends and crossings.
    The buffer is outside the usable corridor width; curved corners are
    approximated with short straight wall panels.
    """
    from ..scenarios import DungeonScenario, MazeScenario
    from ..scenarios.dungeon import dungeon_layout
    if isinstance(scenario, (DungeonScenario, MazeScenario)):
        # Offset by half the thickness, so the requested floor remains usable.
        outline = dungeon_layout(scenario).floor.buffer(WALL_THICKNESS/2, join_style='round', quad_segs=4)
        return tuple((a,b) for ring in (outline.exterior, *outline.interiors)
                     for a,b in zip(list(ring.coords), list(ring.coords)[1:]) if math.dist(a,b)>1e-8)
    points = scenario.points()
    radius = (scenario.width + WALL_THICKNESS) / 2
    outline = LineString(points).buffer(radius, cap_style="round", join_style="round", quad_segs=16)
    polygons = list(outline.geoms) if outline.geom_type == "MultiPolygon" else [outline]
    portals = []
    if math.dist(points[0], points[-1]) > 1e-9:
        for origin, neighbor in ((points[0], points[1]), (points[-1], points[-2])):
            dx, dy = neighbor[0] - origin[0], neighbor[1] - origin[1]
            length = math.hypot(dx, dy)
            portals.append((origin, (dx / length, dy / length)))

    def on_portal(a, b):
        for origin, direction in portals:
            if all((point[0] - origin[0]) * direction[0] +
                   (point[1] - origin[1]) * direction[1] <= 1e-8 and
                   math.dist(point, origin) <= radius + 1e-8 for point in (a, b)):
                return True
        return False

    segments = []
    for polygon in polygons:
        for ring in (polygon.exterior, *polygon.interiors):
            coordinates = list(ring.coords)
            for start, end in zip(coordinates, coordinates[1:]):
                if math.dist(start, end) > 1e-8 and not on_portal(start, end):
                    segments.append((start, end))
    return tuple(segments)
