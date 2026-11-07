"""Shared Scenic placement, persistence, terrain support, and navigation."""
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import mujoco
import numpy as np
from shapely.geometry import LineString, Point

from robo_sim_py import Scenario, Corridor, LoopScenario, MazeScenario, Terrain
from robo_sim_py.scenarios.objects import StaticObjectSettings, StaticBox
from robo_sim_py.scenarios.spatial import placement_geometry
from robo_sim_py.scenarios.population import populate_scenario, static_objects, placement_region, navigation_connected
from robo_sim_py.scenarios.library import ScenarioPreset, parse_preset
from robo_sim_py.simulation import build_model, example_robot
from robo_sim_py.simulation.generation import export_scene
from robo_sim_py.simulation.terrain import HeightField
from robo_sim_py.navigation import plan_scenario
from robo_sim_py.assets import create_controller, controller_mode
from robo_sim_py import cli


def layouts():
    return [Scenario((Corridor(8),Corridor(5,90)),width=2),
            LoopScenario(radius=5,width=2),LoopScenario('figure_eight',radius=5,width=2),
            MazeScenario(rows=3,columns=4)]


class SharedValidationTests(unittest.TestCase):
    def test_empty_legacy_scenarios_and_bad_saved_inputs(self):
        for s in layouts():
            with self.subTest(layout=type(s).__name__):
                with patch.dict('sys.modules',{'scenic':None}):
                    self.assertEqual(static_objects(s),())
                    self.assertEqual(parse_preset(ScenarioPreset('Test','',s).to_dict()).scenario,s)
                for changes in ({'objects':{}},{'static_objects':[]},
                                {'objects':StaticObjectSettings(count=1),'static_objects':()}):
                    with self.assertRaises(ValueError):replace(s,**changes)

    def test_loop_reachability_uses_distinct_anchors(self):
        s=LoopScenario(radius=5,width=2)
        geometry=placement_geometry(s)
        self.assertEqual(len(set(geometry.anchors)),4)
        self.assertTrue(navigation_connected(s,()))
        # Cut both sides of the annulus, separating opposite mission anchors.
        barrier=StaticBox(0,5,14,.2,.4)
        self.assertFalse(navigation_connected(s,(barrier,)))


@unittest.skipUnless(importlib.util.find_spec('scenic'),'Requires Scenic')
class SharedPopulationTests(unittest.TestCase):
    def test_all_families_placement_replay_and_seed_independence(self):
        for base in layouts():
            with self.subTest(layout=type(base).__name__,shape=getattr(base,'shape',None)):
                s=populate_scenario(replace(base,objects=StaticObjectSettings(count=2,seed=7)))
                self.assertEqual(len(s.static_objects),2)
                self.assertEqual(placement_geometry(base).route,placement_geometry(s).route)
                self.assertTrue(navigation_connected(s,s.static_objects))
                self.assertTrue(LineString(s.points()).intersects(s.static_objects[0].footprint()))
                for obj in s.static_objects:
                    self.assertTrue(placement_region(s).buffer(1e-8).covers(obj.footprint()))
                different=populate_scenario(replace(s,objects=replace(s.objects,seed=9),static_objects=None))
                self.assertNotEqual(s.static_objects,different.static_objects)
                payload=json.loads(json.dumps(ScenarioPreset('Placed','',s).to_dict()))
                with patch.dict('sys.modules',{'scenic':None}), tempfile.TemporaryDirectory() as directory:
                    restored=parse_preset(payload).scenario
                    self.assertEqual(restored,s)
                    exported=export_scene(restored,Path(directory)/'scene.xml')
                    model=mujoco.MjModel.from_xml_path(str(exported))
                    for i in range(2):
                        index=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_GEOM,f'static_box_{i}')
                        self.assertGreaterEqual(index,0)
                        self.assertEqual(model.geom_bodyid[index],0)
                        self.assertEqual(model.geom_contype[index],1)
                planned=plan_scenario(s)
                self.assertEqual(planned.points[0],s.points()[0])
                if s.closed:self.assertEqual(planned.points[0],planned.points[-1])
                floor=placement_geometry(s).floor.buffer(-.3)
                for obj in s.static_objects:floor=floor.difference(obj.footprint().buffer(.3))
                for a,b in zip(planned.points,planned.points[1:]):self.assertTrue(floor.buffer(1e-8).covers(LineString((a,b))))
                self.assertEqual(controller_mode(example_robot(),s),'astar')

    def test_clear_route_mode_and_uneven_terrain_support(self):
        for base in (Scenario((Corridor(8),),width=2.5),LoopScenario(radius=6,width=2.5),MazeScenario(rows=3,columns=3)):
            s=populate_scenario(replace(base,objects=StaticObjectSettings(count=2,seed=8,placement='clear-route')))
            for obj in s.static_objects:self.assertFalse(LineString(s.points()).intersects(obj.footprint()))
        for mode in ('waves','random'):
            s=populate_scenario(Scenario((Corridor(6),),width=2,
                terrain=Terrain(mode=mode,height=.02,spacing=1.5),objects=StaticObjectSettings(count=2,seed=7)))
            terrain=HeightField(s)
            model=build_model(example_robot(),s)
            for i,obj in enumerate(s.static_objects):
                index=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_GEOM,f'static_box_{i}')
                bottom=model.geom_pos[index,2]-obj.height/2
                self.assertAlmostEqual(bottom,terrain.support_height(obj.footprint()))
                for x in np.linspace(obj.footprint().bounds[0],obj.footprint().bounds[2],10):
                    for y in np.linspace(obj.footprint().bounds[1],obj.footprint().bounds[3],10):
                        self.assertGreaterEqual(bottom+1e-9,terrain.height(x,y))
            self.assertEqual(controller_mode(example_robot(),s),'line')
            with self.assertRaisesRegex(ValueError,'flat'):controller_mode(example_robot(),s,'astar')

    def test_cli_save_edit_and_clear_across_layouts(self):
        for flags in (['--maze','--maze-rows','3','--maze-columns','3'],
                      ['--corridor','8','0','--width','2'],
                      ['--loop','circle','--radius','5','--width','2']):
            p=cli.selected_preset(cli.parser().parse_args(['scenario',*flags,'--static-objects','2','--object-seed','7']))
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'case.json';path.write_text(json.dumps(p.to_dict()))
                same=cli.selected_preset(cli.parser().parse_args(['scenario','--scenario',str(path)]))
                self.assertEqual(same.scenario,p.scenario)
                edited=cli.selected_preset(cli.parser().parse_args(['scenario','--scenario',str(path),'--object-seed','9']))
                self.assertNotEqual(edited.scenario.static_objects,p.scenario.static_objects)
                cleared=cli.selected_preset(cli.parser().parse_args(['scenario','--scenario',str(path),'--static-objects','0']))
                self.assertEqual(static_objects(cleared.scenario),())

    def test_simple_robot_finishes_populated_maps_and_repeats_loop(self):
        for base in (Scenario((Corridor(6),),width=2),LoopScenario(radius=4,width=2),MazeScenario(rows=2,columns=3,cell_size=2,width=1.6)):
            s=populate_scenario(replace(base,objects=StaticObjectSettings(count=1,seed=7)))
            model=build_model(example_robot(),s);data=mujoco.MjData(model);mujoco.mj_forward(model,data)
            follower=create_controller(example_robot(),model,s)
            obstacles={i for i in range(model.ngeom) if (mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_GEOM,i) or '').startswith(('static_box','corridor_wall'))}
            # One loop plus a short continuation proves it remains a repeating controller.
            duration=follower.plan.length/.13+20
            for _ in range(int(duration/model.opt.timestep)):
                follower.update(data);mujoco.mj_step(model,data)
                self.assertFalse(follower.lost)
                self.assertFalse(any(any(int(g) in obstacles for g in c.geom) for c in data.contact))
                if not s.closed and follower.finished:break
            if s.closed:
                self.assertFalse(follower.finished)
                self.assertGreaterEqual(follower.laps,1)
            else:self.assertTrue(follower.finished)

    def test_shared_gui_controls_and_saved_placements(self):
        from PySide6.QtWidgets import QApplication
        from robo_sim_py.ui.editor import ScenarioWindow
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            w=ScenarioWindow(directory)
            try:
                for base in layouts():
                    s=populate_scenario(replace(base,objects=StaticObjectSettings(count=2,seed=7)))
                    w.dirty=False
                    with patch.dict('sys.modules',{'scenic':None}):
                        w._add_preset(ScenarioPreset('Imported','',s),'Imported')
                        self.assertEqual(w.scenario(),s)
                        self.assertFalse(w.object_panel.isHidden())
                        w.preview.resize(500,400);self.assertFalse(w.preview.grab().isNull())
                    w.object_fields['seed'].setText('9');w._edited()
                    self.assertNotEqual(w.scenario().static_objects,s.static_objects)
                    w.object_fields['count'].setText('0');w._edited()
                    self.assertEqual(static_objects(w.scenario()),())
            finally:
                w.dirty=False;w.close();w.deleteLater();app.processEvents()
