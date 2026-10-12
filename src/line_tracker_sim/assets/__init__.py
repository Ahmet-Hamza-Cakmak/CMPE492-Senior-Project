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

    @property
    def path(self):
        return Path(__file__).parent / self.key / "robot.xml"


EXAMPLES = (
    RobotExample("simple_robot", "Simple two-wheel robot", SimpleFollower),
    RobotExample("google_robot", "Google Robot (mobile adaptation)", GoogleFollower),
)


def example_for_path(path):
    resolved = Path(path).expanduser().resolve()
    return next((example for example in EXAMPLES if example.path.resolve() == resolved), None)


def create_controller(robot_path, model, scenario):
    example = example_for_path(robot_path)
    if example is None:
        raise ValueError("Automatic driving requires a registered example robot.")
    return example.controller(model, scenario)
