"""Track geometry, independent of the GUI and physics engine."""

from dataclasses import dataclass
import math


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
