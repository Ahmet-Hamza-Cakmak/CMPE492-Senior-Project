"""Public imports use the canonical implementation and work together."""
import importlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import navprobe


class PublicApiTests(unittest.TestCase):
    def test_public_exports_use_canonical_implementation(self):
        for public, implementation in (
            ('generation', 'navprobe.simulation.generation'),
            ('controllers', 'navprobe.experiments.controllers'),
            ('robots', 'navprobe.assets'),
        ):
            module = importlib.import_module('navprobe.' + public)
            original = importlib.import_module(implementation)
            for name in module.__all__:
                self.assertIs(getattr(module, name), getattr(original, name))
        for name in ('Scenario', 'MazeScenario', 'ScenarioPreset', 'ControllerContext',
                     'export_scene', 'plan_scenario', 'build_model'):
            self.assertTrue(getattr(navprobe, name).__module__.startswith('navprobe.'))
        self.assertFalse((Path(navprobe.__file__).parent.parent / 'robo_sim_py').exists())
        with self.assertRaises(AttributeError):
            getattr(navprobe, 'unknown_api_operation')

    def test_public_scenario_persistence_planning_and_export(self):
        from navprobe import (
            Corridor, Scenario, StaticBox, StaticObjectSettings, ScenarioPreset,
            export_scene, load_preset, save_preset, plan_scenario, load_scene,
        )
        from navprobe.scenarios import placement_geometry
        scenario = Scenario((Corridor(8),), width=2,
                            objects=StaticObjectSettings(count=1),
                            static_objects=(StaticBox(3, .5, .3, .3, .4),))
        geometry = placement_geometry(scenario)
        route = plan_scenario(scenario)
        self.assertEqual(route.points[0], geometry.anchors[0])
        self.assertEqual(route.points[-1], geometry.anchors[-1])
        with tempfile.TemporaryDirectory() as directory:
            preset = ScenarioPreset('Public API', 'Saved concrete placement', scenario)
            path = save_preset(preset, directory)
            restored = load_preset(path)
            self.assertEqual(restored, preset)
            output = export_scene(restored.scenario, Path(directory) / 'scene.xml')
            self.assertGreater(load_scene(output).ngeom, 0)

    def test_imports_do_not_load_optional_integrations_or_start_interfaces(self):
        result = subprocess.run([sys.executable, '-c', '''
import sys
import navprobe
from navprobe import *
import navprobe.robots, navprobe.experiments
for module in ('mujoco', 'mujoco.viewer', 'PySide6', 'scenic', 'navprobe.cli', 'navprobe.ui.editor'):
    assert module not in sys.modules, module
assert 'export_scene' in dir(navprobe)
'''], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
