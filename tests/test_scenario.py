import base64
import math
from pathlib import Path
import tempfile
import unittest

import mujoco

from robo_sim_py import Corridor, Scenario
from robo_sim_py.simulation import build_model, example_robot


class ScenarioTests(unittest.TestCase):
    def test_relative_turns_and_shared_endpoints(self):
        points = Scenario((Corridor(2), Corridor(3, 90), Corridor(1, -90))).points()
        for actual, expected in zip(points, [(0, 0), (2, 0), (2, 3), (3, 3)]):
            self.assertAlmostEqual(actual[0], expected[0])
            self.assertAlmostEqual(actual[1], expected[1])

    def test_invalid_parameters(self):
        for length in (0, -1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                Corridor(length)
        for angle in (-180, 180, math.nan, math.inf):
            with self.assertRaises(ValueError):
                Corridor(1, angle)
        for sections, width, line in (((), .8, .025), ((Corridor(1, 2),), .8, .025),
                                      ((Corridor(1),), .01, .02), ((Corridor(1),), math.inf, .02)):
            with self.assertRaises(ValueError):
                Scenario(sections, width, line)

    def test_model_physics_and_noncolliding_line(self):
        model = build_model(example_robot(), Scenario((Corridor(2), Corridor(2, 90))))
        self.assertEqual(model.nu, 2)
        for index in range(model.ngeom):
            if model.geom(index).name.startswith("track_line"):
                self.assertEqual(model.geom_contype[index], 0)
                self.assertEqual(model.geom_conaffinity[index], 0)
        data = mujoco.MjData(model)
        for _ in range(500):
            mujoco.mj_step(model, data)
        self.assertTrue(all(math.isfinite(value) for value in data.qpos))
        self.assertGreater(data.qpos[2], 0.03)

    def test_relative_include_and_texture(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "assets").mkdir()
            (path / "assets" / "pixel.png").write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"))
            (path / "body.xml").write_text('<mujocoinclude><body><geom type="sphere" size=".1"/></body></mujocoinclude>')
            source = '<mujoco><asset><texture name="test" type="2d" file="assets/pixel.png"/></asset><worldbody><include file="body.xml"/></worldbody></mujoco>'
            robot = path / "robot.xml"
            robot.write_text(source)
            model = build_model(robot, Scenario((Corridor(1),)))
            self.assertGreaterEqual(model.texture("test").id, 0)
            self.assertEqual(robot.read_text(), source)


if __name__ == "__main__":
    unittest.main()
