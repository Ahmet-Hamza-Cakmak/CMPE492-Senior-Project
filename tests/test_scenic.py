"""Scenic sampling feeds existing presets, CLI, and the generation pipeline."""

from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import random
import tempfile
import unittest

import numpy as np

from robo_sim_py import cli
from robo_sim_py.scenarios.scenic_adapter import sample_scenic, preset_from_parameters
from robo_sim_py.scenarios.library import load_preset


class ScenicParameterTests(unittest.TestCase):
    def test_invalid_sample_rejected(self):
        valid = dict(ground='flat', corridor_count=2, corridor_width=1.0, line_width=.025,
                     corridor_lengths=[2, 3], corridor_angles=[0, 45])
        for update in ({'corridor_count': 2.5}, {'corridor_count': 3}, {'ground': 'waves'},
                       {'corridor_angles': [10, 0]}, {'corridor_width': -1},
                       {'corridor_lengths': [float('nan'), 2]}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                preset_from_parameters({**valid, **update})

    def test_seed_requires_scenic(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(['generate', '--scenic-seed', '7']), 1)


@unittest.skipUnless(importlib.util.find_spec('scenic'), 'Install the scenic extra for integration tests')
class ScenicIntegrationTests(unittest.TestCase):
    def test_reproducible_valid_varied_samples_and_random_state(self):
        # Warm imports before checking that sampling restores RNG state.
        first = sample_scenic(seed=7)
        python_state = random.getstate()
        numpy_state = np.random.get_state()
        self.assertEqual(first, sample_scenic(seed=7))
        self.assertEqual(python_state, random.getstate())
        np.testing.assert_array_equal(numpy_state[1], np.random.get_state()[1])
        samples = [sample_scenic(seed=seed).scenario for seed in range(8)]
        self.assertGreater(len({len(s.corridors) for s in samples}), 1)
        self.assertGreater(len({s.width for s in samples}), 1)
        for scenario in samples:
            self.assertEqual(scenario.terrain.mode, 'flat')
            self.assertTrue(2 <= len(scenario.corridors) <= 8)
            self.assertTrue(.8 <= scenario.width <= 1.5)
            self.assertEqual(scenario.corridors[0].turn, 0)
            self.assertTrue(all(-75 <= part.turn <= 75 for part in scenario.corridors))

    def test_cli_json_xml_and_simulation_use_same_sample(self):
        import mujoco
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            root = Path(directory)
            options = ['--scenic', '--scenic-seed', '7']
            self.assertEqual(cli.main(['scenario', *options, '--output', str(root / 'sample.json')]), 0)
            self.assertEqual(load_preset(root / 'sample.json'), sample_scenic(seed=7))
            self.assertEqual(cli.main(['generate', *options, '--output', str(root / 'scene.xml')]), 0)
            model = mujoco.MjModel.from_xml_path(str(root / 'scene.xml'))
            self.assertEqual(model.nhfield, 0)
            self.assertGreater(model.ngeom, 0)
            _, payload = cli.worker_request(cli.parser().parse_args(['run', *options]))
            self.assertEqual(json.loads(payload)['corridors'], sample_scenic(seed=7).to_dict()['corridors'])

    def test_bad_source_reports_sampling_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'broken.scenic'
            path.write_text('this is invalid scenic syntax !')
            with self.assertRaisesRegex(ValueError, 'Cannot sample Scenic'):
                sample_scenic(path)
