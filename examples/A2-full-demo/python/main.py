"""A short open-loop sequence; it neither follows a line nor completes a lap."""
import json


class Controller:
    def reset(self, model, data, context):
        self.commands = json.loads(context.route_path.read_text())
        self.left = model.actuator("left_motor").id
        self.right = model.actuator("right_motor").id
        self.started = float(data.time)

    def step(self, model, data, context):
        data.ctrl[self.left] = data.ctrl[self.right] = 0
        for command in self.commands:
            if data.time - self.started < command["until"]:
                data.ctrl[self.left] = command["left"]
                data.ctrl[self.right] = command["right"]
                break
        # Zero torque allows coasting; this is not active braking.

    def close(self):
        pass


def create_controller():
    return Controller()
