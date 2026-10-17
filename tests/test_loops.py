import json
import math
import tempfile
import unittest
from unittest.mock import patch

from shapely.geometry import LineString

from robo_sim_py import LoopScenario
from robo_sim_py.scenarios.library import ScenarioPreset, load_preset, parse_preset, save_preset
from robo_sim_py.simulation.walls import WALL_THICKNESS, wall_segments


class LoopTests(unittest.TestCase):
    def test_shapes_close_align_and_keep_the_center_line_clear(self):
        for shape in ("circle", "figure_eight"):
            with self.subTest(shape=shape):
                scenario = LoopScenario(shape, 3)
                points = scenario.points()
                self.assertEqual(points[0], (0, 0))
                self.assertEqual(points[-1], points[0])
                self.assertGreater(points[1][0], 0)
                self.assertAlmostEqual(points[1][1], 0)
                self.assertTrue(all(math.dist(a, b) > 0 for a, b in zip(points, points[1:])))
                route = LineString(points)
                self.assertEqual(route.is_simple, shape == "circle")
                for a, b in wall_segments(scenario):
                    clearance = LineString([a, b]).distance(route) - WALL_THICKNESS / 2
                    self.assertGreater(clearance, scenario.width / 2 - .003)

    def test_round_trip_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            for shape in ("circle", "figure_eight"):
                preset = ScenarioPreset(shape, "Loop test", LoopScenario(shape, 3))
                self.assertEqual(load_preset(save_preset(preset, directory)), preset)
                self.assertEqual(parse_preset(json.loads(json.dumps(preset.to_dict()))), preset)
        for parameters in ({"shape": "unknown"}, {"radius": .1}, {"radius": math.inf}, {"width": -1}):
            with self.assertRaises(ValueError):
                LoopScenario(**parameters)

    def test_viewer_receives_loop_config(self):
        import io
        from robo_sim_py.simulation.__main__ import main
        scenario = LoopScenario("figure_eight", 3)
        payload = json.dumps(ScenarioPreset("Eight", "", scenario).to_dict())
        with patch("sys.argv", ["viewer", "--robot", "example.xml", "--auto-follow"]), \
             patch("sys.stdin", io.StringIO(payload)), \
             patch("robo_sim_py.simulation.__main__.build_model") as build, \
             patch("robo_sim_py.simulation.__main__.run") as run:
            self.assertEqual(main(), 0)
            build.assert_called_once_with("example.xml", scenario)
            run.assert_called_once_with(build.return_value, scenario, auto_follow=True, robot_path="example.xml")
