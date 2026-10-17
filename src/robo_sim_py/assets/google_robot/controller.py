"""Mobile Google Robot controller with arm position holding."""
from ..tracking import DifferentialDriveFollower


class LineFollower(DifferentialDriveFollower):
    def __init__(self, model, scenario):
        super().__init__(model, scenario, body="base_link", radius=0.06435,
                         axle_width=0.36566, speed=0.12, lookahead=0.16,
                         gain=1.5, max_turn=0.65)
        self.holds = [(model.actuator(model.joint(i).name + "_hold").id,
                       0.02 if "finger" in model.joint(i).name else 0.0)
                      for i in range(model.njnt) if model.joint(i).name.startswith("joint_")]

    def update(self, data):
        super().update(data)
        for actuator, position in self.holds:
            data.ctrl[actuator] = position
