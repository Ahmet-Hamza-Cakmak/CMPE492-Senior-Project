import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mujoco

from robo_sim_py.simulation import load_scene, build_model
from robo_sim_py.simulation.__main__ import main


class ImportedSceneTests(unittest.TestCase):
    def test_generated_scene_import_and_robot_selection_error(self):
        from robo_sim_py import Scenario, Corridor
        from robo_sim_py.simulation.generation import export_scene

        with tempfile.TemporaryDirectory() as directory:
            scenario = Scenario((Corridor(2),))
            path = export_scene(scenario, Path(directory) / 'scene.xml')
            self.assertGreater(load_scene(path).ngeom, 0)
            with self.assertRaisesRegex(ValueError, 'Import MuJoCo scene XML'):
                build_model(path, scenario)
            with patch('sys.argv', ['worker', '--scene', str(path)]), \
                 patch('robo_sim_py.simulation.__main__.run') as viewer:
                self.assertEqual(main(), 0)
                self.assertGreater(viewer.call_args.args[0].ngeom, 0)

    def test_scene_keeps_assets_physics_and_robot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'assets').mkdir()
            (root / 'assets' / 'shape.obj').write_text(
                'v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\nf 1 3 2\nf 1 2 4\nf 1 4 3\nf 2 3 4\n')
            (root / 'objects.xml').write_text('''<mujoco><worldbody>
                <geom name="floor" type="plane" size="5 5 .1"/>
                <body name="robot" pos="0 0 2"><freejoint/>
                <geom type="mesh" mesh="shape"/></body>
                </worldbody></mujoco>''')
            path = root / 'scene.xml'
            xml = '''<mujoco><compiler meshdir="assets"/>
                <option timestep=".004" gravity="0 0 -5"/>
                <asset><mesh name="shape" file="shape.obj"/></asset>
                <include file="objects.xml"/></mujoco>'''
            path.write_text(xml)
            model = load_scene(path)
            self.assertEqual(model.ngeom, 2)
            self.assertEqual(model.nmesh, 1)
            self.assertEqual(model.nq, 7)
            self.assertAlmostEqual(model.opt.timestep, .004)
            self.assertEqual(model.opt.gravity[2], -5)
            data = mujoco.MjData(model)
            mujoco.mj_step(model, data)
            self.assertLess(data.qpos[2], 2)
            self.assertEqual(path.read_text(), xml)
            with patch('sys.argv', ['worker', '--scene', str(path)]), \
                 patch('robo_sim_py.simulation.__main__.run') as viewer:
                self.assertEqual(main(), 0)
                self.assertEqual(viewer.call_args.args[0].ngeom, 2)

    def test_missing_and_invalid_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'missing.xml'
            with self.assertRaises(ValueError):
                load_scene(path)
            path.write_text('<broken>')
            with self.assertRaises(ValueError):
                load_scene(path)
