"""BSP topology, physical exports, CLI persistence, and GUI equivalence."""

from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import io
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import mujoco
from shapely.geometry import LineString, Point, box

from robo_sim_py import DungeonScenario, Terrain
from robo_sim_py import cli
from robo_sim_py.scenarios.dungeon import dungeon_layout
from robo_sim_py.scenarios.library import ScenarioPreset, parse_preset, load_preset
from robo_sim_py.simulation import build_model, example_robot, load_scene
from robo_sim_py.simulation.generation import export_scene
from robo_sim_py.simulation.walls import wall_segments


class DungeonTests(unittest.TestCase):
    def test_connected_bounded_repeatable_rectangular_and_circular_rooms(self):
        for shape in ('rectangular', 'circular'):
            for seed in range(20):
                with self.subTest(shape=shape, seed=seed):
                    scenario = DungeonScenario(room_shape=shape, layout_seed=seed)
                    layout = dungeon_layout(scenario)
                    self.assertEqual(len(layout.rooms), scenario.room_count)
                    self.assertEqual(len(layout.edges), scenario.room_count-1)
                    self.assertTrue(layout.floor.is_valid)
                    self.assertEqual(layout.floor.geom_type, 'Polygon')
                    self.assertTrue(box(*layout.bounds).covers(layout.floor))
                    self.assertTrue(layout.floor.covers(LineString(layout.route)))
                    self.assertEqual(layout.route[0], (0,0))
                    self.assertNotEqual(layout.route[-1], (0,0))
                    for room in layout.rooms:
                        self.assertTrue(layout.floor.covers(Point(room.x,room.y)))
                        self.assertTrue(scenario.room_min <= room.width <= scenario.room_max)
                        self.assertTrue(scenario.room_min <= room.height <= scenario.room_max)
                        if shape == 'circular':
                            self.assertEqual(room.width,room.height)
                    self.assertEqual(layout, dungeon_layout(replace(scenario)))
        self.assertNotEqual(dungeon_layout(DungeonScenario(layout_seed=1)).rooms,
                            dungeon_layout(DungeonScenario(layout_seed=2)).rooms)

    def test_invalid_settings_and_infeasible_room_count(self):
        for values in ({'room_count':1}, {'room_count':65}, {'room_count':True}, {'map_width':float('nan')},
                       {'room_shape':'oval'}, {'layout_seed':-1}, {'map_height':0}, {'map_width':201},
                       {'room_min':5,'room_max':4}, {'width':9}, {'terrain':Terrain('waves')},
                       {'map_width':4,'map_height':4,'room_count':6}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                DungeonScenario(**values)

    def test_json_roundtrip_and_versions(self):
        preset = ScenarioPreset('Dungeon', 'test', DungeonScenario(room_shape='circular',layout_seed=9))
        self.assertEqual(preset.to_dict()['version'],3)
        self.assertEqual(parse_preset(preset.to_dict()),preset)
        self.assertEqual(dungeon_layout(parse_preset(preset.to_dict()).scenario),dungeon_layout(preset.scenario))
        for update in ({'room_count':False}, {'type':'loop'}, {'unknown':1}):
            with self.assertRaises(ValueError):
                parse_preset({**preset.to_dict(),**update})

    def test_export_physics_and_wall_boundary(self):
        for shape in ('rectangular','circular'):
            scenario = DungeonScenario(room_shape=shape)
            layout = dungeon_layout(scenario)
            for a,b in wall_segments(scenario):
                mid=Point((a[0]+b[0])/2,(a[1]+b[1])/2)
                self.assertLess(abs(mid.distance(layout.floor)-.01),.001)
            with tempfile.TemporaryDirectory() as directory:
                path=export_scene(scenario,Path(directory)/'scene.xml')
                model=load_scene(path)
                self.assertEqual(model.nhfield,0)
                self.assertGreater(model.ngeom,scenario.room_count)
                self.assertEqual(model.nbody,1)
                robot=build_model(example_robot(),scenario)
                data=mujoco.MjData(robot)
                for _ in range(20):
                    mujoco.mj_step(robot,data)
                self.assertGreater(data.time,0)

    def test_cli_generate_save_and_replay_payload(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            root=Path(directory)
            options=['--dungeon','--rooms','5','--room-shape','circular','--layout-seed','7','--width','1']
            self.assertEqual(cli.main(['scenario',*options,'--output',str(root/'case.json')]),0)
            saved=load_preset(root/'case.json')
            self.assertEqual(saved.scenario.room_count,5)
            self.assertEqual(saved.scenario.room_shape,'circular')
            self.assertEqual(cli.main(['generate','--scenario',str(root/'case.json'),'--output',str(root/'scene.xml')]),0)
            load_scene(root/'scene.xml')
            _,payload=cli.worker_request(cli.parser().parse_args(['run',*options]))
            import json
            self.assertEqual(parse_preset(json.loads(payload)).scenario,saved.scenario)
            self.assertEqual(cli.main(['scenario','--rooms','5']),1)
            self.assertEqual(cli.main(['scenario','--dungeon','--terrain','waves']),1)
            args=cli.parser().parse_args(['run','--scene',str(root/'scene.xml'),'--dungeon'])
            with self.assertRaises(ValueError):
                cli.worker_request(args)


class DungeonGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_edit_preview_import_and_category_switch(self):
        from robo_sim_py.ui.editor import ScenarioWindow
        with tempfile.TemporaryDirectory() as directory:
            window=ScenarioWindow(directory)
            try:
                window.category_choice.setCurrentIndex(window.category_choice.findData('dungeons'))
                self.assertIsInstance(window.scenario(),DungeonScenario)
                window.dungeon_shape.setCurrentIndex(window.dungeon_shape.findData('circular'))
                window.dungeon_fields['layout_seed'].setText('7')
                window.dungeon_fields['room_count'].setText('5')
                scenario=window.scenario()
                self.assertEqual(scenario, DungeonScenario(room_shape='circular',layout_seed=7,room_count=5))
                self.assertEqual(window.preview.scenario,scenario)
                self.assertFalse(window.terrain_card.isEnabled())
                window.preview.resize(600,400)
                self.assertFalse(window.preview.grab().isNull())
                window.dungeon_fields['room_count'].setText('999')
                self.assertFalse(window.launch_button.isEnabled())
                window.dirty=False
                window._add_preset(ScenarioPreset('Saved dungeon','',scenario),'Imported')
                self.assertEqual(window.current_category,'dungeons')
                self.assertEqual(window.scenario(),scenario)
                window.dirty=False
                window.category_choice.setCurrentIndex(window.category_choice.findData('corridors'))
                self.assertTrue(window.terrain_card.isEnabled())
                self.assertFalse(isinstance(window.scenario(),DungeonScenario))
            finally:
                window.dirty=False
                window.close();window.deleteLater();self.app.processEvents()
