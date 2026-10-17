"""Track geometry, independent of the GUI and physics engine."""

from dataclasses import dataclass
import math
from typing import Callable


@dataclass(frozen=True)
class Terrain:
    """Physical surface parameters; height is the peak-to-valley range in metres."""

    mode: str = "flat"
    height: float = 0.003
    spacing: float = 0.8
    resolution: int = 129
    seed: int = 42

    def __post_init__(self):
        if self.mode not in ("flat", "waves", "random"):
            raise ValueError("Terrain must be flat, waves, or random.")
        if not math.isfinite(self.height) or not 0 <= self.height <= 0.3:
            raise ValueError("Terrain height variation must be between 0 and 0.3 m.")
        if not math.isfinite(self.spacing) or not 0.1 <= self.spacing <= 10:
            raise ValueError("Terrain spacing must be between 0.1 and 10 m.")
        if type(self.resolution) is not int or not 33 <= self.resolution <= 513:
            raise ValueError("Terrain resolution must be an integer between 33 and 513.")
        if type(self.seed) is not int or not 0 <= self.seed <= 2147483647:
            raise ValueError("Terrain seed must be an integer from 0 to 2147483647.")


@dataclass(frozen=True)
class Corridor:
    length: float
    turn: float = 0.0

    def __post_init__(self):
        if not math.isfinite(self.length) or self.length <= 0:
            raise ValueError("Every corridor length must be finite and greater than zero.")
        if not math.isfinite(self.turn) or not -180 < self.turn < 180:
            raise ValueError("Turn angles must be finite and strictly between -180 and 180 degrees.")


@dataclass(frozen=True)
class Scenario:
    corridors: tuple[Corridor, ...]
    width: float = 0.8
    line_width: float = 0.025
    terrain: Terrain = Terrain()

    @property
    def closed(self):
        return False

    @property
    def total_length(self):
        return sum(part.length for part in self.corridors)

    def __post_init__(self):
        if not 1 <= len(self.corridors) <= 100:
            raise ValueError("Choose between 1 and 100 corridors.")
        if self.corridors[0].turn != 0:
            raise ValueError("The first corridor must have a zero turn angle.")
        if not math.isfinite(self.width) or not math.isfinite(self.line_width):
            raise ValueError("Widths must be finite.")
        if not 0 < self.line_width < self.width:
            raise ValueError("Line width must be positive and smaller than corridor width.")

    def points(self):
        """Shared endpoints ensure consecutive sections have no gaps."""
        points = [(0.0, 0.0)]
        heading = 0.0
        for corridor in self.corridors:
            heading += math.radians(corridor.turn)
            x, y = points[-1]
            points.append((x + corridor.length * math.cos(heading),
                           y + corridor.length * math.sin(heading)))
        return points


@dataclass(frozen=True)
class CircuitDefinition:
    """Register a closed circuit by supplying unaligned points for a size in metres."""
    label: str
    size_label: str
    generate: Callable[[float], list[tuple[float, float]]]


def _circle(radius):
    return [(radius * math.sin(2*math.pi*i/96), radius * (1-math.cos(2*math.pi*i/96)))
            for i in range(96)]


def _figure_eight(radius):
    angles = [2*math.pi*i/128 + math.pi/4 for i in range(128)]
    return [(radius*math.sin(t), radius*math.sin(t)*math.cos(t)) for t in angles]


CIRCUITS = {
    "circle": CircuitDefinition("Circular circuit", "Radius (m)", _circle),
    "figure_eight": CircuitDefinition("Figure-eight circuit", "Circuit scale (m)", _figure_eight),
}


def register_circuit(key, definition):
    """Trusted installed extensions call this before loading their scenario presets."""
    if not isinstance(key, str) or not key.isidentifier() or key in CIRCUITS:
        raise ValueError("Circuit key must be a new Python identifier.")
    if not isinstance(definition, CircuitDefinition) or not callable(definition.generate):
        raise ValueError("Supply a CircuitDefinition with a generator.")
    CIRCUITS[key] = definition


@dataclass(frozen=True)
class LoopScenario:
    """Smooth closed tracks sampled as short segments, starting along +X."""

    shape: str = "circle"
    radius: float = 2.0
    width: float = 0.8
    line_width: float = 0.025
    terrain: Terrain = Terrain()

    def __post_init__(self):
        if self.shape not in CIRCUITS:
            raise ValueError(f"Unknown circuit: {self.shape}. Available: {', '.join(CIRCUITS)}")
        if not all(math.isfinite(value) for value in (self.radius, self.width, self.line_width)):
            raise ValueError("Loop dimensions must be finite.")
        if not 0 < self.line_width < self.width:
            raise ValueError("Line width must be positive and smaller than track width.")
        if not 2 * self.width <= self.radius <= 1000:
            raise ValueError("Loop radius/scale must be at least twice its width and at most 1000 m.")

    @property
    def closed(self):
        return True

    def points(self):
        raw = list(CIRCUITS[self.shape].generate(self.radius))
        if len(raw) < 3 or not all(len(p) == 2 and all(math.isfinite(v) for v in p) for p in raw):
            raise ValueError("Circuit generators must return at least three finite XY points.")
        if raw[-1] == raw[0]:
            raw.pop()
        if len(raw) < 3 or any(a == b for a, b in zip(raw, raw[1:])):
            raise ValueError("Circuit points must contain at least three distinct consecutive positions.")
        # Align the first chord with the unchanged bundled robot spawn pose.
        origin = raw[0]
        raw = [(x - origin[0], y - origin[1]) for x, y in raw]
        heading = math.atan2(raw[1][1], raw[1][0])
        c, s = math.cos(heading), math.sin(heading)
        points = [(c*x + s*y, -s*x + c*y) for x, y in raw]
        points.append(points[0])
        return points

    @property
    def total_length(self):
        points = self.points()
        return sum(math.dist(a, b) for a, b in zip(points, points[1:]))
