"""Robot-aware generation: real collision bounds, connectivity, and interface parity."""
import io
import json
import math
from contextlib import redirect_stderr
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from navprobe import (Corridor, Scenario, StaticBox, StaticObjectSettings, ScenarioPreset,
                      estimate_robot_footprint, prepare_scenario, example_robot)
from navprobe import cli


class FootprintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def robot(self, bodies, assets=''):
        path = self.root/'robot.xml'
        path.write_text(f'<mujoco>{assets}<worldbody><geom type="plane" size="100 100 .1"/>{bodies}</worldbody></mujoco>')
        return path
    def test_world_and_visual_geometry_excluded_and_offset_children_enclosed(self):
        path = self.robot('''<body name="base" pos="20 -10 1"><freejoint/>
          <geom type="box" size=".2 .1 .05"/>
          <geom type="sphere" size="50" contype="0" conaffinity="0" mass="0"/>
          <body pos=".4 0 0"><geom type="box" size=".1 .1 .05"/></body>
          </body>''')
        f = estimate_robot_footprint(path, margin=.02)
        self.assertEqual(f.geometry_count, 2)
        self.assertAlmostEqual(f.raw_radius, math.hypot(.5, .1))
        self.assertAlmostEqual(f.radius, f.raw_radius+.02)
    def test_rotated_mesh_and_articulated_children(self):
        path = self.robot('''<body name="base"><freejoint/>
          <geom type="box" size=".1 .1 .1"/>
          <body pos=".5 0 0" euler="0 0 90"><joint type="hinge"/>
          <geom type="mesh" mesh="tetra"/></body></body>''',
          '<asset><mesh name="tetra" vertex="0 0 0  .2 0 0  0 .1 0  0 0 .1"/></asset>')
        f = estimate_robot_footprint(path, margin=0)
        self.assertEqual(f.geometry_count, 2)
        self.assertGreaterEqual(f.radius+1e-7, .5)
        self.assertLess(f.radius, .8)
    def test_ambiguous_models_and_manual_override(self):
        path = self.robot('<body name="a"><geom size=".1"/></body><body name="b" pos="5 0 0"><geom size=".2"/></body>')
        with self.assertRaisesRegex(ValueError, 'single robot tree'):
            estimate_robot_footprint(path)
        self.assertGreater(estimate_robot_footprint(path, body='b').radius, .2)
        result, inferred = prepare_scenario(Scenario((Corridor(4),)), robot_path=path, robot_radius=.2)
        self.assertIsNone(inferred)
        self.assertEqual(result.objects.robot_radius, .2)
        with self.assertRaisesRegex(ValueError, 'Unknown robot body'):
            estimate_robot_footprint(path, body='missing')
    def test_narrow_floor_rejected_even_without_obstacles(self):
        path = self.robot('<body name="base"><geom type="box" size=".6 .4 .1"/></body>')
        with self.assertRaisesRegex(ValueError, 'Enlarge passages'):
            prepare_scenario(Scenario((Corridor(4),), width=.8), robot_path=path)
        for margin in (-1, float('nan')):
            with self.assertRaises(ValueError):
                estimate_robot_footprint(path, margin=margin)
    def test_saved_placements_rechecked_not_resampled(self):
        scenario = Scenario((Corridor(6),), width=1.2,
                            objects=StaticObjectSettings(count=1, min_size=.2, robot_radius=.1),
                            static_objects=(StaticBox(3, 0, .6, .6, .4),))
        # A .1 m circle can pass; a .4 m circle cannot pass this box.
        with self.assertRaisesRegex(ValueError, 'block'):
            prepare_scenario(scenario, robot_radius=.4)
        accepted, _ = prepare_scenario(scenario, robot_radius=.1)
        self.assertEqual(accepted.static_objects, scenario.static_objects)
    def test_cli_generation_and_run_share_resolved_footprint(self):
        scenario = Scenario((Corridor(4),), width=1.2)
        source = self.root/'scenario.json'
        source.write_text(json.dumps(ScenarioPreset('Test','',scenario).to_dict()))
        with redirect_stderr(io.StringIO()):
            preset = cli.selected_preset(cli.parser().parse_args(['scenario','--scenario',str(source),'--robot','simple_robot']))
            _, payload = cli.worker_request(cli.parser().parse_args(['run','--scenario',str(source)]))
        self.assertAlmostEqual(preset.scenario.objects.robot_radius, estimate_robot_footprint(example_robot()).radius)
        self.assertEqual(json.loads(payload)['objects']['robot_radius'], preset.scenario.objects.robot_radius)
    def test_scenic_sampling_uses_inferred_radius(self):
        from unittest.mock import patch
        path = example_robot()
        settings = StaticObjectSettings(count=1)
        scenario = Scenario((Corridor(6),), width=2, objects=settings)
        seen=[]
        def sample(case):
            seen.append(case.objects.robot_radius)
            return replace(case, static_objects=(StaticBox(3,.4,.3,.3,.4),))
        with patch('navprobe.scenarios.population.populate_scenario', side_effect=sample):
            result, footprint = prepare_scenario(scenario, robot_path=path)
        self.assertEqual(seen, [footprint.radius])
        self.assertEqual(result.objects.robot_radius, footprint.radius)
