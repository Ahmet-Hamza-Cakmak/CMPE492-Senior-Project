"""Controller tuned for the small two-wheel example."""
from ..tracking import DifferentialDriveFollower


class LineFollower(DifferentialDriveFollower):
    def __init__(self, model, scenario):
        super().__init__(model, scenario)
