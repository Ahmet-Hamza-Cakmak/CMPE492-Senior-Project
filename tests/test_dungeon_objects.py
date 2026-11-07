"""Spatial Scenic population, frozen replay, collisions and both user interfaces."""

from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import mujoco
import numpy as np

from robo_sim_py import DungeonScenario
from robo_sim_py import cli
from robo_sim_py.scenarios.objects import StaticObjectSettings, StaticBox
from robo_sim_py.scenarios.dungeon import dungeon_layout
from robo_sim_py.scenarios.dungeon_population import (
    populate_dungeon, dungeon_objects, placement_region, validate_objects, _sample,
)
from robo_sim_py.scenarios.library import ScenarioPreset, parse_preset
from robo_sim_py.simulation.generation import export_scene


class ObjectValidationTests(unittest.TestCase):
    def test_settings_and_boxes_reject_invalid_parameters(self):
        for settings in ({'count':True}, {'count':31}, {'seed':-1}, {'max_size':.1},
                         {'height':0}, {'clearance':-1}, {'min_size':float('nan')}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                StaticObjectSettings(**settings)
        with self.assertRaises(ValueError):
            StaticBox(float('inf'),0,.3,.3,.4)

    def test_zero_objects_do_not_need_scenic_and_invalid_saved_positions_fail(self):
        scenario= DungeonScenario()
        with patch.dict('sys.modules',{'scenic':None}):
            self.assertEqual(dungeon_objects(scenario),())
        configured=replace(scenario,objects=StaticObjectSettings(count=1))
        for box in (StaticBox(0,0,.3,.3,.4),StaticBox(999,999,.3,.3,.4)):
            with self.assertRaises(ValueError):
                replace(configured,static_objects=(box,))
        with self.assertRaises(ValueError):
            replace(configured,static_objects=())
        with redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(['scenario','--static-objects','2']),1)

    def test_missing_dependency_is_an_actionable_error(self):
        scenario=DungeonScenario(objects=StaticObjectSettings(count=1,seed=874921))
        _sample.cache_clear()
        with patch.dict('sys.modules',{'scenic':None}), self.assertRaisesRegex(ValueError,'pip install'):
            populate_dungeon(scenario)


@unittest.skipUnless(importlib.util.find_spec('scenic'),'Requires the optional scenic extra')
class ScenicDungeonPopulationTests(unittest.TestCase):
    def test_placement_regions_pair_clearance_and_independent_seeds(self):
        for shape in ('rectangular','circular'):
            base=DungeonScenario(room_shape=shape,layout_seed=7)
            samples=[]
            for seed in (1,2):
                case=populate_dungeon(replace(base,objects=StaticObjectSettings(count=4,seed=seed)))
                objects=dungeon_objects(case)
                self.assertEqual(len(objects),4)
                self.assertEqual(objects,dungeon_objects(replace(case,static_objects=None)))
                self.assertEqual(dungeon_layout(base).rooms,dungeon_layout(case).rooms)
                self.assertEqual(dungeon_layout(base).route,dungeon_layout(case).route)
                region=placement_region(case)
                for i,obj in enumerate(objects):
                    self.assertTrue(region.buffer(1e-8).covers(obj.footprint()))
                    for other in objects[:i]:
                        self.assertGreaterEqual(obj.footprint().distance(other.footprint()),case.objects.clearance-1e-8)
                samples.append(objects)
            self.assertNotEqual(*samples)

    def test_navigation_obstructs_reference_but_retains_robot_sized_path(self):
        from shapely.geometry import LineString
        from robo_sim_py.scenarios.dungeon_population import navigation_connected
        for seed in (7, 42):
            scenario=populate_dungeon(DungeonScenario(objects=StaticObjectSettings(count=3,seed=seed)))
            self.assertEqual((scenario.map_width,scenario.map_height),(200,200))
            self.assertEqual(scenario.width,3)
            self.assertTrue(LineString(scenario.points()).intersects(scenario.static_objects[0].footprint()))
            self.assertTrue(navigation_connected(scenario,scenario.static_objects))
            clean=replace(scenario,objects=replace(scenario.objects,placement='clear-route'),static_objects=None)
            clear=populate_dungeon(clean)
            for obj in clear.static_objects:
                self.assertFalse(LineString(clear.points()).intersects(obj.footprint()))

    def test_connectivity_rejects_barrier_but_allows_detour(self):
        from robo_sim_py.scenarios.dungeon_population import navigation_connected
        small=DungeonScenario(map_width=16,map_height=12,room_min=2,room_max=4,width=.8)
        layout=dungeon_layout(small)
        # A vertical barrier spanning the entire map disconnects opposite endpoints.
        a,b=layout.route[0],layout.route[-1]
        if abs(a[0]-b[0]) > 1:
            mid=(a[0]+b[0])/2
            barrier=StaticBox(mid,(layout.bounds[1]+layout.bounds[3])/2,.2,100,.4)
        else:
            mid=(a[1]+b[1])/2
            barrier=StaticBox((layout.bounds[0]+layout.bounds[2])/2,mid,100,.2,.4)
        self.assertTrue(navigation_connected(small,()))
        self.assertFalse(navigation_connected(small,(barrier,)))

    def test_saved_concrete_placements_replay_without_scenic(self):
        scenario=populate_dungeon(DungeonScenario(objects=StaticObjectSettings(count=3)))
        payload=ScenarioPreset('Populated','',scenario).to_dict()
        self.assertEqual(len(payload['static_objects']),3)
        with patch.dict('sys.modules',{'scenic':None}), tempfile.TemporaryDirectory() as directory:
            restored=parse_preset(json.loads(json.dumps(payload))).scenario
            self.assertEqual(restored,scenario)
            self.assertEqual(dungeon_objects(restored),scenario.static_objects)
            path=export_scene(restored,Path(directory)/'scene.xml')
            model=mujoco.MjModel.from_xml_path(str(path))
            self.assertEqual(model.nbody,1)
            data=mujoco.MjData(model);mujoco.mj_forward(model,data)
            for i,obj in enumerate(scenario.static_objects):
                geom_id=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_GEOM,f'static_box_{i}')
                self.assertEqual(model.geom_contype[geom_id],1)
                self.assertEqual(model.geom_bodyid[geom_id],0)
                np.testing.assert_allclose(model.geom_pos[geom_id],[obj.x,obj.y,obj.height/2],atol=1e-4)
                hit=np.array([-1],dtype=np.int32)
                distance=mujoco.mj_ray(model,data,np.array([obj.x,obj.y,3.]),np.array([0.,0.,-1.]),None,True,-1,hit)
                self.assertEqual(hit[0],geom_id)
                self.assertAlmostEqual(3-distance,obj.height,places=4)
        with self.assertRaises(ValueError):
            replace(scenario,static_objects=(scenario.static_objects[0],)*3)

    def test_impossible_population_reports_failure(self):
        case=DungeonScenario(map_width=16,map_height=12,room_min=2,room_max=4,width=.8,
                             objects=StaticObjectSettings(count=30,min_size=3,max_size=3))
        with self.assertRaisesRegex(ValueError,'space|place'):
            populate_dungeon(case)

    def test_cli_json_export_and_edit_preserve_or_resample(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            root=Path(directory)
            opts=['--dungeon','--static-objects','3','--object-seed','7']
            self.assertEqual(cli.main(['scenario',*opts,'--output',str(root/'case.json')]),0)
            payload=json.loads((root/'case.json').read_text())
            self.assertEqual(len(payload['static_objects']),3)
            self.assertEqual(cli.main(['generate','--scenario',str(root/'case.json'),'--output',str(root/'scene.xml')]),0)
            model=mujoco.MjModel.from_xml_path(str(root/'scene.xml'))
            self.assertGreaterEqual(mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_GEOM,'static_box_2'),0)
            edited=cli.selected_preset(cli.parser().parse_args(['scenario','--scenario',str(root/'case.json'),'--object-seed','8']))
            self.assertNotEqual(edited.scenario.static_objects,parse_preset(payload).scenario.static_objects)
            self.assertEqual(dungeon_layout(edited.scenario).rooms,dungeon_layout(parse_preset(payload).scenario).rooms)
            disabled=cli.selected_preset(cli.parser().parse_args(['scenario','--scenario',str(root/'case.json'),'--static-objects','0']))
            self.assertEqual(dungeon_objects(disabled.scenario),())

    def test_gui_population_preview_and_imported_sample(self):
        from PySide6.QtWidgets import QApplication
        from robo_sim_py.ui.editor import ScenarioWindow
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            window=ScenarioWindow(directory)
            try:
                window.category_choice.setCurrentIndex(window.category_choice.findData('dungeons'))
                window.object_fields['count'].setText('3')
                window.object_fields['seed'].setText('7')
                window._edited()
                case=window.scenario()
                self.assertEqual(len(case.static_objects),3)
                self.assertEqual(window.preview.scenario,case)
                window.preview.resize(600,400)
                self.assertFalse(window.preview.grab().isNull())
                preset=parse_preset(ScenarioPreset('Saved objects','',case).to_dict())
                window.dirty=False
                with patch.dict('sys.modules',{'scenic':None}):
                    window._add_preset(preset,'Imported')
                    self.assertEqual(window.scenario(),case)
                window.object_fields['count'].setText('100')
                window._edited()
                self.assertFalse(window.launch_button.isEnabled())
            finally:
                window.dirty=False
                window.close();window.deleteLater();app.processEvents()
