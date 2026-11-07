"""Controller tuned for the small two-wheel example."""
from ..tracking import DifferentialDriveFollower


class LineFollower(DifferentialDriveFollower):
    def __init__(self, model, scenario):
        super().__init__(model, scenario)


class NavigationFollower(DifferentialDriveFollower):
    """Plan around static geometry, then use unchanged physical speed and gains."""

    def __init__(self, model, scenario, *, resolution=.25, clearance=None):
        from ...navigation import plan_scenario
        self.plan = plan_scenario(scenario, resolution=resolution, clearance=clearance)

        class Route:
            closed = scenario.closed

            def points(inner):
                return list(self.plan.points)

        super().__init__(model, Route())
