"""Serializable static geometry and placement settings, independent of Scenic."""

from dataclasses import dataclass
import math

from shapely.affinity import rotate, translate
from shapely.geometry import box


def positive(value, label, *, zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (value < 0 if zero else value <= 0):
        raise ValueError(f'{label} must be a finite {"nonnegative" if zero else "positive"} number.')


@dataclass(frozen=True)
class StaticObjectSettings:
    count: int = 0
    seed: int = 42
    min_size: float = .25
    max_size: float = .6
    height: float = .4
    clearance: float = .1
    placement: str = "navigation"
    robot_radius: float = .3

    def __post_init__(self):
        if type(self.count) is not int or not 0 <= self.count <= 30:
            raise ValueError('Static object count must be an integer from 0 to 30.')
        if type(self.seed) is not int or not 0 <= self.seed <= 2147483647:
            raise ValueError('Static object seed must be an integer from 0 to 2147483647.')
        for name in ('min_size', 'max_size', 'height'):
            positive(getattr(self, name), 'Object ' + name)
        if self.placement not in ('navigation', 'clear-route'):
            raise ValueError('Object placement must be navigation or clear-route.')
        positive(self.robot_radius, 'Robot clearance radius')
        if self.robot_radius > 2:
            raise ValueError('Robot clearance radius must not exceed 2 m.')
        positive(self.clearance, 'Object clearance', zero=True)
        if not self.min_size <= self.max_size <= 3 or self.height > 3 or self.clearance > 2:
            raise ValueError('Require object min size <= max size <= 3 m, height <= 3 m, and clearance <= 2 m.')


@dataclass(frozen=True)
class StaticBox:
    x: float
    y: float
    width: float
    length: float
    height: float
    yaw: float = 0.0  # radians, counterclockwise about +Z

    def __post_init__(self):
        for name in ('x', 'y', 'yaw'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'Object {name} must be finite.')
        for name in ('width', 'length', 'height'):
            positive(getattr(self, name), 'Object ' + name)

    def footprint(self):
        return translate(rotate(box(-self.width/2, -self.length/2, self.width/2, self.length/2),
                                self.yaw, use_radians=True, origin=(0, 0)), self.x, self.y)


def validate_population(scenario):
    """Validate shared configuration and saved placements, without sampling."""
    if not isinstance(scenario.objects, StaticObjectSettings):
        raise ValueError('Objects must be StaticObjectSettings.')
    saved = scenario.static_objects
    if saved is not None:
        if not isinstance(saved, tuple) or not all(isinstance(obj, StaticBox) for obj in saved):
            raise ValueError('Concrete static objects must be an immutable tuple.')
        from .population import validate_objects
        validate_objects(scenario, saved)
