"""Shared planar placement geometry for all generated layout families."""

from dataclasses import dataclass
from functools import lru_cache

from shapely.geometry import LineString


@dataclass(frozen=True)
class PlacementGeometry:
    floor: object
    route: tuple
    anchors: tuple
    passages: tuple = ()


@lru_cache(maxsize=32)
def placement_geometry(scenario):
    from . import DungeonScenario, MazeScenario
    if isinstance(scenario, (DungeonScenario, MazeScenario)):
        from .dungeon import dungeon_layout
        layout = dungeon_layout(scenario)
        return PlacementGeometry(layout.floor, layout.route,
                                 (layout.route[0], layout.route[-1]), layout.passages)
    route = tuple(scenario.points())
    line = LineString(route)
    floor = line.buffer(scenario.width/2, cap_style='round', join_style='round', quad_segs=16)
    # A closed route needs distinct mission anchors; start==goal alone is vacuous.
    anchors = tuple(tuple(line.interpolate(line.length*i/4).coords)[0] for i in range(4)) if scenario.closed else (route[0],route[-1])
    return PlacementGeometry(floor, route, anchors)
