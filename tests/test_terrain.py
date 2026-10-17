import unittest

import mujoco
import numpy as np

from robo_sim_py import Corridor, Scenario, LoopScenario, Terrain
from robo_sim_py.scenarios.library import ScenarioPreset, parse_preset
from robo_sim_py.simulation import build_model, example_robot
from robo_sim_py.simulation.terrain import HeightField
from robo_sim_py.assets import create_controller


class TerrainTests(unittest.TestCase):
    def test_repeatable_bounded_and_level_start(self):
        def make(seed):
            return HeightField(Scenario((Corridor(2),), terrain=Terrain('random', seed=seed)))
        field = make(42)
        np.testing.assert_array_equal(field.heights, make(42).heights)
        self.assertFalse(np.array_equal(field.heights, make(43).heights))
        self.assertAlmostEqual(field.heights.min(), 0)
        self.assertAlmostEqual(field.heights.max(), .003)
        self.assertEqual(field.height(0, 0), 0)

    def test_json_round_trip_and_legacy(self):
        for scenario in (Scenario((Corridor(2),), terrain=Terrain('random', .02, 1, 257, 8)),
                         LoopScenario(terrain=Terrain('waves'))):
            preset = ScenarioPreset('Terrain test', 'test', scenario)
            payload = preset.to_dict()
            self.assertEqual(parse_preset(payload).scenario, scenario)
            del payload['terrain']
            self.assertEqual(parse_preset(payload).scenario.terrain, Terrain())
        for kwargs in ({'height': -.1}, {'spacing': 0}, {'resolution': 1000}, {'seed': -1}):
            with self.assertRaises(ValueError):
                Terrain(**kwargs)

    def test_physical_surface_matches_height(self):
        scenario = Scenario((Corridor(2),), terrain=Terrain('waves'))
        field = HeightField(scenario)
        model = build_model(example_robot(), scenario)
        self.assertEqual(model.nhfield, 1)
        self.assertFalse(any((mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) or '').startswith('track_floor')
                             for i in range(model.ngeom)))
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        for x in (1., 1.4, 1.8):
            distance = mujoco.mj_ray(model, data, np.array([x, 0., 2.]), np.array([0., 0., -1.]),
                                     None, True, -1, np.array([-1], dtype=np.int32))
            self.assertAlmostEqual(2-distance, field.height(x, 0), delta=.0002)

    def test_examples_drive_on_both_surfaces(self):
        for robot in ('simple_robot', 'google_robot'):
            for mode in ('waves', 'random'):
                with self.subTest(robot=robot, mode=mode):
                    scenario = Scenario((Corridor(1.5),), terrain=Terrain(mode, height=.003))
                    path = example_robot(robot)
                    model = build_model(path, scenario)
                    data = mujoco.MjData(model)
                    mujoco.mj_forward(model, data)
                    controller = create_controller(path, model, scenario)
                    touched = False
                    ground = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, 'environment_ground')
                    for step in range(25000):
                        controller.update(data)
                        mujoco.mj_step(model, data)
                        if step % 100 == 0:
                            touched |= any(ground in contact.geom for contact in data.contact)
                        self.assertFalse(controller.lost)
                        if controller.finished:
                            break
                    self.assertTrue(touched)
                    if robot == 'simple_robot':
                        self.assertTrue(controller.finished, str(data.qpos[:3]))
                    # Google's flat-ground controller can stall near the endpoint on a slope.
                    self.assertGreater(data.qpos[0], 1.0)
                    self.assertTrue(np.all(np.isfinite(data.qpos)))
