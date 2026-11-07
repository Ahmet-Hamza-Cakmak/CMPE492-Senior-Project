"""Scenic population of generated environments; concrete placements replay without Scenic."""

from dataclasses import replace
from functools import lru_cache
import math
from pathlib import Path
import random

from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from .spatial import placement_geometry
from .objects import StaticBox


def placement_region(scenario):
    layout = placement_geometry(scenario)
    protected = [Point(point).buffer(max(.65, scenario.objects.robot_radius)) for point in layout.anchors]
    if scenario.objects.placement == 'clear-route':
        from . import DungeonScenario
        if isinstance(scenario, DungeonScenario):
            protected += [LineString(path).buffer(scenario.width/2 + .05, cap_style='square', join_style='mitre')
                          for path in layout.passages]
        protected.append(LineString(layout.route).buffer(max(.4, scenario.objects.robot_radius)))
    return layout.floor.buffer(-scenario.objects.clearance).difference(unary_union(protected))


def navigation_connected(scenario, objects):
    """Planar connectivity for a circular robot; no 3D terrain feasibility claim."""
    layout = placement_geometry(scenario)
    radius = scenario.objects.robot_radius
    free = layout.floor.buffer(-radius)
    if objects:
        free = free.difference(unary_union([obj.footprint() for obj in objects]).buffer(radius))
    regions = list(free.geoms) if free.geom_type == 'MultiPolygon' else [free]
    return any(all(region.covers(Point(point)) for point in layout.anchors) for region in regions)


def scenic_boxes(objects):
    return tuple(StaticBox(float(obj.position.x), float(obj.position.y), float(obj.width),
                           float(obj.length), float(obj.height), float(obj.yaw)) for obj in objects)


def validate_objects(scenario, objects):
    settings = scenario.objects
    if len(objects) != settings.count:
        raise ValueError('Saved static object count does not match the placement settings.')
    region = placement_region(scenario)
    footprints = []
    for obj in objects:
        if not isinstance(obj, StaticBox):
            raise ValueError('Static placements must be StaticBox records.')
        if not (settings.min_size <= obj.width <= settings.max_size and
                settings.min_size <= obj.length <= settings.max_size and
                math.isclose(obj.height, settings.height)):
            raise ValueError('Saved static object dimensions do not match placement settings.')
        footprint = obj.footprint()
        if not region.buffer(1e-8).covers(footprint):
            raise ValueError('Static object intersects a wall or a protected placement region.')
        if any(footprint.distance(other) < settings.clearance - 1e-8 or footprint.intersection(other).area > 1e-10
               for other in footprints):
            raise ValueError('Static objects overlap or violate the requested clearance.')
        footprints.append(footprint)
    if objects and settings.placement == 'navigation' and not navigation_connected(scenario, objects):
        raise ValueError('Objects block the start-to-goal path for the configured robot radius.')
    return tuple(objects)


@lru_cache(maxsize=32)
def _sample(scenario):
    try:
        import scenic
        import numpy as np
        from scenic.core.regions import PolygonalRegion
    except ImportError as exc:
        raise ValueError('Static object placement requires Scenic: python -m pip install "navprobe[scenic]" (or ".[scenic]" from a checkout)') from exc
    from .scenic_adapter import _SAMPLING_LOCK
    region = placement_region(scenario)
    if region.is_empty or region.area < scenario.objects.count * scenario.objects.min_size**2:
        raise ValueError('Not enough placement space; reduce object count/size/clearance or enlarge passages/rooms.')
    settings = scenario.objects
    route_region = LineString(placement_geometry(scenario).route).buffer(.02).intersection(region)
    if settings.placement == 'navigation' and (route_region.is_empty or not navigation_connected(scenario, ())):
        raise ValueError('No navigable mission anchors or route placement region for this robot radius; increase passage width or reduce radius.')
    def connectivity_check(objects):
        return settings.placement != 'navigation' or navigation_connected(scenario, scenic_boxes(objects))
    params = dict(placement_region=PolygonalRegion(polygon=region), object_count=settings.count,
                  min_size=settings.min_size, max_size=settings.max_size,
                  object_height=settings.height, object_clearance=settings.clearance,
                  first_region=PolygonalRegion(polygon=route_region) if settings.placement == 'navigation' else PolygonalRegion(polygon=region),
                  connectivity_check=connectivity_check)
    with _SAMPLING_LOCK:
        python_state, numpy_state = random.getstate(), np.random.get_state()
        try:
            random.seed(settings.seed)
            np.random.seed(settings.seed)
            specification = scenic.scenarioFromFile(
                str(Path(__file__).with_name('scenic') / 'dungeon_static.scenic'), params=params)
            scene, _ = specification.generate(maxIterations=2000)
            objects = scenic_boxes(scene.objects)
            return validate_objects(scenario, objects)
        except Exception as exc:
            raise ValueError(f'Scenic could not place all static objects: {exc}. Reduce count/size/clearance or enlarge passages/rooms.') from exc
        finally:
            random.setstate(python_state)
            np.random.set_state(numpy_state)


def static_objects(scenario):
    if scenario.static_objects is not None:
        return validate_objects(scenario, scenario.static_objects)
    if scenario.objects.count == 0:
        return ()
    return _sample(scenario)


def populate_scenario(scenario):
    """Freeze a sample so a worker or saved JSON does not need to resample."""
    if scenario.static_objects is not None or scenario.objects.count == 0:
        return scenario
    return replace(scenario, static_objects=static_objects(scenario))


# Compatibility aliases for saved integrations and existing dungeon callers.
dungeon_objects = static_objects
populate_dungeon = populate_scenario
