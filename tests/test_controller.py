import math
import unittest

import mujoco

from line_tracker_sim import Corridor, Scenario
from line_tracker_sim.assets import create_controller
from line_tracker_sim.simulation import build_model, example_robot


class ControllerTests(unittest.TestCase):
    example = "simple_robot"

    def setup_simulation(self, sections):
        scenario = Scenario(tuple(Corridor(*section) for section in sections))
        path = example_robot(self.example)
        model = build_model(path, scenario)
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        return scenario, model, data, create_controller(path, model, scenario)

    def test_tracks_and_stops_using_physics(self):
        routes = [((1.2, 0),), ((.6, 0), (.6, 90)), ((.6, 0), (.6, -90)),
                  ((.6, 0), (.6, 135)), ((2, 0), (2, 90), (1.5, -45))]
        for route in routes:
            with self.subTest(route=route):
                scenario, model, data, controller = self.setup_simulation(route)
                max_error = 0.0
                for _ in range(25000):
                    controller.update(data)
                    mujoco.mj_step(model, data)
                    x, y = data.xpos[controller.body, :2]
                    errors = []
                    for a, b in zip(scenario.points(), scenario.points()[1:]):
                        dx, dy = b[0] - a[0], b[1] - a[1]
                        t = max(0, min(1, ((x-a[0])*dx + (y-a[1])*dy)/(dx*dx+dy*dy)))
                        errors.append(math.hypot(x-a[0]-t*dx, y-a[1]-t*dy))
                    max_error = max(max_error, min(errors))
                    self.assertFalse(controller.lost)
                    if controller.finished:
                        break
                self.assertTrue(controller.finished, f"Did not finish; position: {data.qpos[:3]}")
                self.assertLess(max_error, 0.10)
                for _ in range(500):
                    controller.update(data)
                    mujoco.mj_step(model, data)
                goal = scenario.points()[-1]
                self.assertLess(math.dist(data.qpos[:2], goal), 0.06)
                self.assertLess(math.hypot(*data.qvel[:2]), 0.01)
                self.assertGreater(data.qpos[2], 0.05)

    def test_lost_line_brakes_and_reset_restarts(self):
        _, model, data, controller = self.setup_simulation(((1, 0),))
        data.qpos[1] = 0.5
        mujoco.mj_forward(model, data)
        controller.update(data)
        self.assertTrue(controller.lost)
        self.assertTrue(all(data.ctrl[index] == 0 for index in controller.motors))
        controller.finished = True
        controller.last_time = 5
        mujoco.mj_resetData(model, data)
        mujoco.mj_forward(model, data)
        controller.update(data)
        self.assertFalse(controller.finished)
        self.assertFalse(controller.lost)
        for _ in range(500):
            controller.update(data)
            mujoco.mj_step(model, data)
        self.assertGreater(data.qpos[0], 0.05)


class GoogleControllerTests(ControllerTests):
    example = "google_robot"
