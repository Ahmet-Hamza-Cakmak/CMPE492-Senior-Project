import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from line_tracker_sim.scenarios.library import (
    BUNDLED_DIRECTORY, discover_presets, load_preset, save_preset, user_scenario_directory,
)


class PresetTests(unittest.TestCase):
    def test_user_library_location_stays_compatible(self):
        with patch("sys.platform", "linux"), patch.dict("os.environ", {"XDG_DATA_HOME": "/tmp/example-data"}):
            self.assertEqual(user_scenario_directory(), Path("/tmp/example-data/line-tracker-sim/scenarios"))

    def test_bundled_and_round_trip(self):
        presets, errors = discover_presets(BUNDLED_DIRECTORY)
        self.assertFalse(errors)
        self.assertGreaterEqual(len(presets), 4)
        with tempfile.TemporaryDirectory() as directory:
            original = presets[0][1]
            first = save_preset(original, directory)
            second = save_preset(original, directory)
            self.assertNotEqual(first, second)
            self.assertEqual(load_preset(first), original)
            self.assertEqual(load_preset(second), original)

    def test_invalid_files_do_not_hide_valid_presets(self):
        valid = discover_presets(BUNDLED_DIRECTORY)[0][0][1]
        with tempfile.TemporaryDirectory() as directory:
            save_preset(valid, directory)
            path = Path(directory) / "invalid.json"
            for content in ("{", "[]", '{"version": 42}',
                            json.dumps({**valid.to_dict(), "width": True}),
                            json.dumps({**valid.to_dict(), "line_width": -1}),
                            json.dumps({**valid.to_dict(), "width": float("nan")})):
                with self.subTest(content=content):
                    path.write_text(content)
                    presets, errors = discover_presets(directory)
                    self.assertEqual(len(presets), 1)
                    self.assertEqual(len(errors), 1)

    def test_bundled_tracks_complete_with_both_examples(self):
        import math
        import mujoco
        from line_tracker_sim.assets import EXAMPLES, create_controller
        from line_tracker_sim.simulation import build_model

        for _, preset in discover_presets(BUNDLED_DIRECTORY)[0]:
            for example in EXAMPLES:
                with self.subTest(preset=preset.name, robot=example.key):
                    model = build_model(example.path, preset.scenario)
                    data = mujoco.MjData(model)
                    mujoco.mj_forward(model, data)
                    controller = create_controller(example.path, model, preset.scenario)
                    # Allow slow robots enough simulated time for the route length.
                    laps = 2 if preset.scenario.closed else 1
                    seconds = laps * preset.scenario.total_length / 0.06 + 20
                    for _ in range(int(seconds / model.opt.timestep)):
                        controller.update(data)
                        mujoco.mj_step(model, data)
                        if controller.finished or controller.lost or controller.laps >= laps:
                            break
                    if preset.scenario.closed:
                        self.assertGreaterEqual(controller.laps, 2)
                        self.assertFalse(controller.finished)
                    else:
                        self.assertTrue(controller.finished)
                    self.assertFalse(controller.lost)
                    self.assertLess(math.dist(data.xpos[controller.body, :2], preset.scenario.points()[-1]), 0.06)
