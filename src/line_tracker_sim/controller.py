"""Ideal geometric line sensing and motor control for the bundled robot.

This baseline uses the known, ordered center line and simulator pose. It is
not an optical sensor model and must not be used to evaluate perception.
"""

import math


def clamp(value, low, high):
    return max(low, min(high, value))


class LineFollower:
    """Look-ahead steering with wheel-speed feedback and limited motor torque."""

    def __init__(self, model, scenario):
        self.points = scenario.points()
        self.lengths = [section.length for section in scenario.corridors]
        self.body = model.body("robot").id
        self.motors = [model.actuator(name).id for name in ("left_motor", "right_motor")]
        self.dofs = [int(model.joint(name).dofadr[0]) for name in ("left_axle", "right_axle")]
        self.limits = [model.actuator_ctrlrange[index].copy() for index in self.motors]
        self.reset()

    def reset(self):
        self.segment = 0
        self.finished = False
        self.lost = False
        self.last_time = -1.0

    def update(self, data):
        if data.time < self.last_time:
            self.reset()
        self.last_time = data.time
        x, y = data.xpos[self.body, :2]
        rotation = data.xmat[self.body].reshape(3, 3)
        yaw = math.atan2(rotation[1, 0], rotation[0, 0])
        start, end = self.points[self.segment:self.segment + 2]
        length = self.lengths[self.segment]
        ux, uy = (end[0] - start[0]) / length, (end[1] - start[1]) / length
        along = clamp((x - start[0]) * ux + (y - start[1]) * uy, 0, length)
        # Advance only in route order, including at self-intersections.
        if self.segment < len(self.lengths) - 1 and length - along < 0.06:
            self.segment += 1
            start, end = self.points[self.segment:self.segment + 2]
            length = self.lengths[self.segment]
            ux, uy = (end[0] - start[0]) / length, (end[1] - start[1]) / length
            along = clamp((x - start[0]) * ux + (y - start[1]) * uy, 0, length)
        distance = math.hypot(x - start[0] - along * ux, y - start[1] - along * uy)
        self.lost = distance > 0.30
        remaining = length - along + sum(self.lengths[self.segment + 1:])
        if self.segment == len(self.lengths) - 1 and math.hypot(x - end[0], y - end[1]) < 0.045:
            self.finished = True

        # Walk 12 cm ahead along the connected line to anticipate corners.
        target_segment, target_along = self.segment, along + 0.12
        while target_segment < len(self.lengths) - 1 and target_along > self.lengths[target_segment]:
            target_along -= self.lengths[target_segment]
            target_segment += 1
        a, b = self.points[target_segment:target_segment + 2]
        fraction = min(1, target_along / self.lengths[target_segment])
        tx, ty = a[0] + fraction * (b[0] - a[0]), a[1] + fraction * (b[1] - a[1])
        error = math.atan2(math.sin(math.atan2(ty - y, tx - x) - yaw),
                           math.cos(math.atan2(ty - y, tx - x) - yaw))
        speed = min(0.16, remaining * 0.8) * max(0, math.cos(error)) ** 2
        turn = clamp(4.0 * error, -1.8, 1.8)
        if self.finished or self.lost or data.time < 0.25:
            speed = turn = 0.0
        # Wheel radius 4 cm, axle track 14 cm; +Y joint axes drive forward.
        targets = [(speed - turn * 0.07) / 0.04, (speed + turn * 0.07) / 0.04]
        for motor, dof, target, (low, high) in zip(self.motors, self.dofs, targets, self.limits):
            data.ctrl[motor] = clamp(0.012 * (target - data.qvel[dof]), low, high)
