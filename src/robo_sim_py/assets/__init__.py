"""Explicit registry: only bundled, trusted controller code is executed."""

from dataclasses import dataclass
from pathlib import Path

from .simple_robot.controller import LineFollower as SimpleFollower
from .google_robot.controller import LineFollower as GoogleFollower


@dataclass(frozen=True)
class RobotExample:
    key: str
    label: str
    controller: type
    model_path: Path | None = None
    spawn: tuple[float, float, float, float] = (0, 0, 0, 0)

    @property
    def path(self):
        return Path(self.model_path) if self.model_path is not None else Path(__file__).parent / self.key / "robot.xml"


EXAMPLES = [
    RobotExample("simple_robot", "Simple two-wheel robot", SimpleFollower),
    RobotExample("google_robot", "Google Robot (mobile adaptation)", GoogleFollower),
]


def register_robot(example):
    """Register trusted installed robots before creating the editor window."""
    import math
    if not isinstance(example, RobotExample) or not example.key.isidentifier():
        raise ValueError("Supply a RobotExample with an identifier key.")
    if any(item.key == example.key or item.path.resolve() == example.path.resolve() for item in EXAMPLES):
        raise ValueError("Robot key and model path must be unique.")
    if not example.path.is_file() or not callable(example.controller):
        raise ValueError("Robot needs an existing XML file and controller factory.")
    if len(example.spawn) != 4 or not all(math.isfinite(value) for value in example.spawn):
        raise ValueError("Robot spawn must contain four finite values.")
    EXAMPLES.append(example)


def example_for_path(path):
    resolved = Path(path).expanduser().resolve()
    return next((example for example in EXAMPLES if example.path.resolve() == resolved), None)


def create_controller(robot_path, model, scenario):
    example = example_for_path(robot_path)
    if example is None:
        raise ValueError("Automatic driving requires a registered example robot.")
    return example.controller(model, scenario)
