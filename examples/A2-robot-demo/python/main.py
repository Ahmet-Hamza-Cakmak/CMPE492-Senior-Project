"""Example adapter: use the supplied route with this robot's existing follower."""
from robo_sim_py.assets.simple_robot.controller import LineFollower


class Controller:
    def reset(self, model, data, context):
        if context.scenario is None:
            raise ValueError("This controller needs a generated track.")
        self.follower = LineFollower(model, context.scenario)

    def step(self, model, data, context):
        self.follower.update(data)

    def close(self):
        pass


def create_controller():
    return Controller()
