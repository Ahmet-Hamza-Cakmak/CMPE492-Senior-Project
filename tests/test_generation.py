"""Pipeline composition and exported scene round trips without a viewer."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import mujoco
import numpy as np

from robo_sim_py import Corridor, Scenario, LoopScenario, Terrain
from robo_sim_py import cli
from robo_sim_py.simulation.generation import (
    GenerationPipeline, generate_spec, export_scene, ground_stage, walls_stage,
)


class GenerationTests(unittest.TestCase):
    def test_later_stage_can_use_ground_and_walls(self):
        visited = []

        def extension(context):
            self.assertIsNotNone(context.terrain)
            self.assertGreaterEqual(context.height(1, 0), 0)
            self.assertTrue(any(g.name.startswith('corridor_wall_') for g in context.spec.geoms))
            visited.append(True)

        pipeline = GenerationPipeline((ground_stage, walls_stage, extension))
        generate_spec(Scenario((Corridor(2),), terrain=Terrain('waves')), pipeline=pipeline).compile()
        self.assertEqual(visited, [True])

    def test_exports_reload_after_moving_and_preserve_physics(self):
        for mode in ('flat', 'waves', 'random'):
            for closed in (False, True):
                with self.subTest(mode=mode, closed=closed), tempfile.TemporaryDirectory() as directory:
                    terrain = Terrain(mode)
                    scenario = (LoopScenario('circle', terrain=terrain) if closed else
                                Scenario((Corridor(2), Corridor(1, 90)), terrain=terrain))
                    root = Path(directory)
                    original = root / 'original'
                    original.mkdir()
                    scene = export_scene(scenario, original / 'scene & ground.xml')
                    expected = generate_spec(scenario).compile()
                    moved = root / 'moved'
                    original.rename(moved)
                    actual = mujoco.MjModel.from_xml_path(str(moved / scene.name))
                    self.assertEqual(actual.ngeom, expected.ngeom)
                    self.assertEqual(actual.nbody, 1)  # environment only
                    np.testing.assert_allclose(actual.geom_pos, expected.geom_pos, atol=1e-5)
                    np.testing.assert_allclose(actual.hfield_data, expected.hfield_data, atol=1e-6)
                    np.testing.assert_array_equal(actual.tex_data, expected.tex_data)
                    self.assertEqual((moved / 'scene & ground_assets').exists(), mode != 'flat')
                    before = (moved / scene.name).read_bytes()
                    with self.assertRaises(FileExistsError):
                        export_scene(scenario, moved / scene.name)
                    self.assertEqual((moved / scene.name).read_bytes(), before)

    def test_cli_generate_does_not_start_app_or_worker(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(cli, 'start_worker') as worker:
            output = Path(directory) / 'scene.xml'
            with redirect_stdout(io.StringIO()):
                code = cli.main(['generate', '--loop', 'figure_eight', '--terrain', 'random',
                                 '--seed', '8', '--output', str(output)])
            self.assertEqual(code, 0)
            worker.assert_not_called()
            mujoco.MjModel.from_xml_path(str(output))

    def test_asset_collision_and_failed_generation_leave_no_xml(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scene_assets').mkdir()
            scenario = Scenario((Corridor(2),), terrain=Terrain('random'))
            with self.assertRaises(FileExistsError):
                export_scene(scenario, root / 'scene.xml')
            self.assertFalse((root / 'scene.xml').exists())
            shutil.rmtree(root / 'scene_assets')
            coarse = Scenario((Corridor(100),), terrain=Terrain('waves'))
            with self.assertRaises(ValueError):
                export_scene(coarse, root / 'scene.xml')
            self.assertFalse((root / 'scene.xml').exists())
            self.assertFalse((root / 'scene_assets').exists())
