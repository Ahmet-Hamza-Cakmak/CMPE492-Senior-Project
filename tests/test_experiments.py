import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import zipfile

import mujoco
import numpy as np

from robo_sim_py import Corridor, Scenario, LoopScenario
from robo_sim_py.experiments import open_package, run_assignment
from robo_sim_py.experiments.controllers import load_controller, place_robot
from robo_sim_py.scenarios import CIRCUITS, CircuitDefinition, register_circuit
from robo_sim_py.scenarios.library import ScenarioPreset
from robo_sim_py.simulation import build_model, load_scene, run, example_robot
from robo_sim_py.simulation.__main__ import main

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'


def make_zip(destination, mode='robot', extra=None):
    """Build fixtures from the maintained example source, not generated archives."""
    directory = EXAMPLES / f'A2-{mode}-demo'
    with zipfile.ZipFile(destination, 'w') as archive:
        for file in directory.rglob('*'):
            if file.is_file() and '__pycache__' not in file.parts:
                archive.write(file, file.relative_to(directory.parent))
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return destination


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.zip = self.root / 'test.zip'

    def tearDown(self):
        self.temp.cleanup()

    def test_manifest_free_assignment_any_zip_name_and_persistent_outputs(self):
        import os
        import sys
        zip_path = self.root / "anything with spaces ü.zip"
        menagerie = self.root / "local-models"
        menagerie.mkdir()
        (menagerie / "model.xml").write_text("<mujoco/>")
        entry = """from pathlib import Path
import sys
import helper
assert __name__ == '__main__'
assert len(sys.argv) == 1
assert Path('scenes/circuit.xml').is_file()
assert Path('mujoco_menagerie/model.xml').is_file()
assert (Path(__file__).resolve().parents[2] / 'mujoco_menagerie/model.xml').is_file()
assert Path('data').is_dir()
Path('data/result.txt').write_text(helper.VALUE)
"""
        for prefix in ('', 'any folder name/'):
            with self.subTest(prefix=prefix):
                with zipfile.ZipFile(zip_path, 'w') as archive:
                    archive.writestr(prefix + 'data/', '')
                    archive.writestr(prefix + 'python/main.py', entry)
                    archive.writestr(prefix + 'python/helper.py', "VALUE = 'completed'")
                    archive.writestr(prefix + 'scenes/circuit.xml', '<mujoco/>')
                destination = self.root / ('run-flat' if not prefix else 'run-nested')
                cwd, argv = os.getcwd(), sys.argv[:]
                with open_package(zip_path, menagerie_directory=menagerie) as experiment:
                    self.assertEqual(experiment.mode, 'standalone')
                    with patch('sys.stdout', io.StringIO()):
                        run_assignment(experiment, destination)
                self.assertEqual(os.getcwd(), cwd)
                self.assertEqual(sys.argv, argv)
                self.assertEqual((destination / 'assignment/data/result.txt').read_text(), 'completed')
                self.assertTrue((menagerie / 'model.xml').exists())
                sys.modules.pop('helper', None)

    def test_standalone_worker_and_exception_keep_outputs(self):
        with zipfile.ZipFile(self.zip, 'w') as archive:
            archive.writestr('python/main.py', "from pathlib import Path\nPath('result.txt').write_text('started')\nraise RuntimeError('example failure')")
            archive.writestr('scenes/circuit.xml', '<mujoco/>')
        destination = self.root / 'failed-run'
        digest = hashlib.sha256(self.zip.read_bytes()).hexdigest()
        with patch('sys.argv', ['worker', '--package', str(self.zip), '--approved-sha256', digest,
                               '--run-directory', str(destination)]), \
             patch('sys.stderr', io.StringIO()) as errors, patch('sys.stdout', io.StringIO()):
            self.assertEqual(main(), 1)
            self.assertIn('example failure', errors.getvalue())
        self.assertEqual((destination / 'assignment/result.txt').read_text(), 'started')

    def test_examples_load_drive_and_cleanup(self):
        for mode in ('full', 'robot'):
            make_zip(self.zip, mode)
            with open_package(self.zip) as e:
                extracted = e.root
                self.assertEqual(e.mode, mode)
                scenario = Scenario((Corridor(1.2),)) if mode == 'robot' else None
                model = build_model(e.model_path, scenario) if scenario else load_scene(e.model_path)
                controller, context = load_controller(e, scenario)
                self.assertEqual(context.route, tuple(scenario.points()) if scenario else None)
                data = mujoco.MjData(model)
                mujoco.mj_forward(model, data)
                controller.reset(model, data, context)
                for _ in range(1000):
                    controller.step(model, data, context)
                    mujoco.mj_step(model, data)
                self.assertGreater(data.qpos[0], .1)
                self.assertTrue(np.isfinite(data.qpos).all())
                controller.close()
            self.assertFalse(extracted.exists())

    def test_manifest_inspection_never_imports_code_and_hash_binds_approval(self):
        make_zip(self.zip)
        with open_package(self.zip) as e:
            original_digest = e.digest
            self.assertEqual(original_digest, hashlib.sha256(self.zip.read_bytes()).hexdigest())
        # Replace the entry point with a failure: inspection must still succeed.
        with zipfile.ZipFile(self.zip) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        entries['A2-robot-demo/python/main.py'] = b'raise RuntimeError("Code executed")'
        with zipfile.ZipFile(self.zip, 'w') as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        with open_package(self.zip):
            pass
        with self.assertRaisesRegex(ValueError, 'changed after approval'):
            with open_package(self.zip, expected_digest=original_digest):
                pass

    def test_archive_rejects_traversal_links_ambiguity_and_limits(self):
        for path in ('../escape', '/escape', 'C:/escape', 'A2-robot-demo/../../escape', 'bad\\path'):
            make_zip(self.zip, extra={path: 'bad'})
            with self.subTest(path=path), self.assertRaises(ValueError):
                with open_package(self.zip):
                    pass
        make_zip(self.zip)
        with zipfile.ZipFile(self.zip, 'a') as archive:
            info = zipfile.ZipInfo('A2-robot-demo/link')
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, '/tmp')
        with self.assertRaisesRegex(ValueError, 'links'):
            with open_package(self.zip):
                pass
        make_zip(self.zip, extra={'extra/experiment.json': '{}'})
        with self.assertRaisesRegex(ValueError, 'one experiment.json'):
            with open_package(self.zip):
                pass
        make_zip(self.zip)
        with patch('robo_sim_py.experiments.MAX_EXPANDED', 10), self.assertRaisesRegex(ValueError, 'expanded'):
            with open_package(self.zip):
                pass

    def test_local_menagerie_and_missing_files(self):
        menagerie = self.root / 'menagerie'
        menagerie.mkdir()
        (menagerie / 'robot.xml').write_text('<mujoco><worldbody><geom size=".1"/></worldbody></mujoco>')
        manifest = {'version': 1, 'name': 'External dependency', 'mode': 'full',
                    'scene': 'scenes/scene.xml', 'controller': 'python/main.py', 'menagerie': True}
        with zipfile.ZipFile(self.zip, 'w') as archive:
            archive.writestr('experiment.json', json.dumps(manifest))
            archive.writestr('python/main.py', '# not imported')
            archive.writestr('scenes/scene.xml',
                             '<mujoco><include file="../../mujoco_menagerie/robot.xml"/></mujoco>')
        with open_package(self.zip, menagerie_directory=menagerie) as e:
            self.assertEqual(load_scene(e.model_path).ngeom, 1)
        self.assertTrue((menagerie / 'robot.xml').exists())
        with self.assertRaises(ValueError):
            with open_package(self.zip, menagerie_directory=self.root / 'missing'):
                pass
        with zipfile.ZipFile(self.zip, 'w') as archive:
            archive.writestr('experiment.json', json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'existing'):
            with open_package(self.zip):
                pass

    def test_spawn_applies_before_data_creation_and_reset(self):
        model = build_model(example_robot(), Scenario((Corridor(2),)))
        original = model.qpos0.copy()
        place_robot(model, (1, 2, .1, 90))
        data = mujoco.MjData(model)
        np.testing.assert_allclose(data.qpos[:3], [1, 2, original[2]+.1])
        np.testing.assert_allclose(data.qpos[3:7], [2**-.5, 0, 0, 2**-.5], atol=1e-12)
        mujoco.mj_resetData(model, data)
        np.testing.assert_allclose(data.qpos, model.qpos0)

    def test_worker_dispatch_and_missing_approval(self):
        for mode in ('full', 'robot'):
            make_zip(self.zip, mode)
            digest = hashlib.sha256(self.zip.read_bytes()).hexdigest()
            payload = json.dumps(ScenarioPreset('Track', '', Scenario((Corridor(1),))).to_dict())
            with patch('sys.argv', ['worker', '--package', str(self.zip), '--approved-sha256', digest]), \
                 patch('sys.stdin', io.StringIO(payload)), \
                 patch('robo_sim_py.simulation.__main__.run') as viewer:
                self.assertEqual(main(), 0)
                self.assertIn('controller', viewer.call_args.kwargs)
                self.assertEqual(viewer.call_args.args[1] is None, mode == 'full')
                self.assertFalse(viewer.call_args.kwargs['context'].root.exists())
        with patch('sys.argv', ['worker', '--package', str(self.zip)]), \
             patch('sys.stderr', io.StringIO()) as errors:
            self.assertEqual(main(), 1)
            self.assertIn('approval', errors.getvalue())

    def test_viewer_controller_reset_step_and_cleanup_on_failure(self):
        model = load_scene(example_robot())
        controller = MagicMock()
        context = object()
        viewer = MagicMock()
        viewer.cam = mujoco.MjvCamera()
        viewer.is_running.side_effect = [True, True, True, False]
        def reset_during_sync():
            # The actual data instance is captured by the controller step.
            data = controller.step.call_args.args[1]
            mujoco.mj_resetData(model, data)
        # First step advances time; second sync simulates a viewer reset.
        sync_count = 0
        def sync():
            nonlocal sync_count
            sync_count += 1
            if sync_count == 2:
                reset_during_sync()
        viewer.sync.side_effect = sync
        manager = MagicMock()
        manager.__enter__.return_value = viewer
        with patch('mujoco.viewer.launch_passive', return_value=manager), patch('time.sleep'):
            run(model, controller=controller, context=context)
        self.assertEqual(controller.reset.call_count, 2)
        self.assertEqual(controller.step.call_count, 3)
        controller.close.assert_called_once()
        controller.reset_mock()
        controller.step.side_effect = RuntimeError('Controller failure')
        viewer.is_running.side_effect = [True]
        with patch('mujoco.viewer.launch_passive', return_value=manager), self.assertRaisesRegex(RuntimeError, 'failure'):
            run(model, controller=controller, context=context)
        controller.close.assert_called_once()

    def test_registered_circuit_needs_no_editor_or_renderer_branch(self):
        register_circuit('test_square', CircuitDefinition('Square', 'Scale (m)',
                         lambda r: [(0, 0), (r, 0), (r, r), (0, r)]))
        try:
            scenario = LoopScenario('test_square')
            self.assertEqual(scenario.points()[0], scenario.points()[-1])
            self.assertAlmostEqual(scenario.total_length, 8)
            self.assertGreater(build_model(example_robot(), scenario).ngeom, 0)
        finally:
            CIRCUITS.pop('test_square')
