"""Maze graph invariants, geometric walls, persistence and both interfaces."""
from dataclasses import replace
import json
import io
from contextlib import redirect_stdout
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import mujoco
from shapely.geometry import LineString, Point

from robo_sim_py import MazeScenario, Terrain
from robo_sim_py.scenarios.maze import ALGORITHMS, maze_layout
from robo_sim_py.scenarios.library import ScenarioPreset, parse_preset, load_preset, save_preset
from robo_sim_py import cli
from robo_sim_py.simulation import build_model, example_robot
from robo_sim_py.simulation.generation import export_scene
from robo_sim_py.assets import create_controller, controller_mode
from robo_sim_py.navigation import plan_dungeon


class MazeTests(unittest.TestCase):
    def test_graph_connected_tree_and_reference_shortest_route(self):
        for algorithm in ALGORITHMS:
            for seed in (0,7,42):
                with self.subTest(algorithm=algorithm,seed=seed):
                    s=MazeScenario(rows=5,columns=6,algorithm=algorithm,layout_seed=seed)
                    layout=maze_layout(s)
                    self.assertEqual(len(layout.edges),29)
                    self.assertEqual(len({tuple(sorted(e)) for e in layout.edges}),29)
                    seen={0}
                    while True:
                        expanded=seen | {b for a,b in layout.edges if a in seen} | {a for a,b in layout.edges if b in seen}
                        if expanded==seen:break
                        seen=expanded
                    self.assertEqual(len(seen),30)
                    self.assertEqual(layout.route[0],(0.,0.))
                    self.assertTrue(layout.floor.is_valid)
                    self.assertTrue(layout.floor.buffer(1e-8).covers(LineString(layout.route)))
                    self.assertEqual(layout,maze_layout(s))
                    self.assertNotEqual(layout.edges,maze_layout(replace(s,layout_seed=seed+1)).edges)

    def test_growing_tree_endpoints_and_loops(self):
        s=MazeScenario(rows=4,columns=5)
        self.assertEqual(maze_layout(s).edges,maze_layout(replace(s,algorithm='growing-tree',newest_probability=1)).edges)
        for algorithm in ALGORITHMS:
            base=replace(s,algorithm=algorithm)
            partial=maze_layout(replace(base,loop_fraction=.5))
            full=maze_layout(replace(base,loop_fraction=1))
            all_edges=4*(5-1)+(4-1)*5
            self.assertEqual(len(full.edges),all_edges)
            self.assertEqual(len(partial.edges),19+(all_edges-19)//2)
            self.assertEqual(set(maze_layout(base).edges)-set(partial.edges),set())

    def test_invalid_settings(self):
        self.assertEqual(MazeScenario(cell_size=1.2,width=1.1).cell_size,1.2)
        for values in ({'rows':1},{'columns':41},{'rows':True},{'layout_seed':-1},
                       {'cell_size':2.05},{'cell_size':float('nan')},{'cell_size':-1},
                       {'cell_size':101},{'width':0},{'width':3},
                       {'loop_fraction':1.1},{'newest_probability':-1},
                       {'algorithm':'invalid'},{'terrain':Terrain(mode='waves')}):
            with self.subTest(values=values),self.assertRaises(ValueError):MazeScenario(**values)

    def test_bundled_maze_presets_are_listed_as_mazes(self):
        output=io.StringIO()
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(output):
            cli.execute(cli.parser().parse_args(['list','presets','--library',directory]))
        for algorithm in ALGORITHMS:
            lines=[line for line in output.getvalue().splitlines() if 'maze_'+algorithm in line]
            self.assertEqual(len(lines),1)
            self.assertTrue(lines[0].endswith('\tmaze'))

    def test_json_roundtrip_rejects_unknown_fields(self):
        s=MazeScenario(algorithm='growing-tree',newest_probability=.8,loop_fraction=.2,layout_seed=13)
        preset=ScenarioPreset('Maze','Repeatable',s)
        self.assertEqual(parse_preset(json.loads(json.dumps(preset.to_dict()))),preset)
        with self.assertRaises(ValueError):parse_preset({**preset.to_dict(),'unknown':1})
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_preset(save_preset(preset,directory)),preset)

    def test_cli_overrides_and_scene_restrictions(self):
        flags=['--maze','--maze-algorithm','growing-tree','--maze-rows','4','--maze-columns','5',
               '--cell-size','2','--width','1.5','--newest-probability','.7','--loop-fraction','.2','--layout-seed','9']
        args=cli.parser().parse_args(['run',*flags,'--navigation','astar'])
        command,payload=cli.worker_request(args)
        s=parse_preset(json.loads(payload)).scenario
        self.assertEqual((s.rows,s.columns,s.layout_seed),(4,5,9))
        self.assertEqual(s.algorithm,'growing-tree')
        self.assertIn('astar',command)
        with tempfile.TemporaryDirectory() as directory:
            path=save_preset(ScenarioPreset('Maze','',s),directory)
            edited=cli.selected_preset(cli.parser().parse_args(['scenario','--scenario',str(path),'--maze-rows','3']))
            self.assertEqual(edited.scenario.rows,3)
            self.assertEqual(edited.scenario.columns,5)
        for flags in (['--maze','--terrain','waves'],
                      ['--maze','--rooms','3'],['--maze-algorithm','prim'],['--maze-rows','1','--maze']):
            with self.subTest(flags=flags),self.assertRaises(ValueError):
                cli.selected_preset(cli.parser().parse_args(['scenario',*flags]))
        with self.assertRaisesRegex(ValueError,'cannot modify'):
            cli.worker_request(cli.parser().parse_args(['run','--scene','missing.xml','--maze']))

    def test_export_and_collision_walls_match_graph(self):
        s=MazeScenario(rows=3,columns=4)
        model=build_model(example_robot(),s)
        layout=maze_layout(s)
        # Ray from cell centre to each neighbour: open edges have no wall;
        # closed edges must hit a generated wall before the neighbouring cell.
        edges={tuple(sorted(e)) for e in layout.edges}
        for y in range(s.rows):
            for x in range(s.columns):
                a=y*s.columns+x
                for dy,dx in ((0,1),(1,0)):
                    if y+dy>=s.rows or x+dx>=s.columns:continue
                    b=(y+dy)*s.columns+x+dx
                    origin=[x*s.cell_size,y*s.cell_size,.15]
                    import numpy as np
                    geom=np.array([-1],dtype=np.int32)
                    # mj_forward computes geom transforms before ray queries.
                    data=mujoco.MjData(model);mujoco.mj_forward(model,data)
                    distance=mujoco.mj_ray(model,data,np.array(origin),np.array([dx,dy,0.],dtype=float),None,1,-1,geom)
                    # Ignore robot by starting the ray away from its spawn body.
                    if a==0:continue
                    if tuple(sorted((a,b))) in edges:
                        self.assertTrue(distance<0 or distance>s.cell_size-.01)
                    else:self.assertTrue(0<distance<s.cell_size)
        with tempfile.TemporaryDirectory() as directory:
            path=export_scene(s,Path(directory)/'maze.xml')
            exported=mujoco.MjModel.from_xml_path(str(path))
            self.assertGreater(exported.ngeom,20)
            self.assertEqual(exported.nu,0)

    def test_astar_routes_and_physical_execution(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                s=MazeScenario(rows=2,columns=3,cell_size=1.5,width=1.1,algorithm=algorithm,layout_seed=7)
                self.assertEqual(controller_mode(example_robot(),s),'astar')
                plan=plan_dungeon(s)
                free=maze_layout(s).floor.buffer(-.3)
                for a,b in zip(plan.points,plan.points[1:]):self.assertTrue(free.covers(LineString((a,b))))
                model=build_model(example_robot(),s)
                data=mujoco.MjData(model);mujoco.mj_forward(model,data)
                controller=create_controller(example_robot(),model,s)
                walls={i for i in range(model.ngeom) if (mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_GEOM,i) or '').startswith('corridor_wall')}
                for _ in range(int((plan.length/.06+30)/model.opt.timestep)):
                    controller.update(data);mujoco.mj_step(model,data)
                    self.assertFalse(controller.lost)
                    self.assertFalse(any(any(int(g) in walls for g in c.geom) for c in data.contact))
                    if controller.finished:break
                self.assertTrue(controller.finished)


class MazeEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_gui_edit_save_import_and_launch(self):
        from robo_sim_py.ui.editor import ScenarioWindow
        with tempfile.TemporaryDirectory() as directory:
            w=ScenarioWindow(directory)
            try:
                w.category_choice.setCurrentIndex(w.category_choice.findData('mazes'))
                for algorithm in ALGORITHMS:
                    w.maze_algorithm.setCurrentIndex(w.maze_algorithm.findData(algorithm))
                    self.assertEqual(w.scenario().algorithm,algorithm)
                    self.assertEqual(w.maze_fields['newest_probability'].isEnabled(),algorithm=='growing-tree')
                w.maze_fields['rows'].setText('4');w.maze_fields['columns'].setText('5')
                w.maze_fields['loop_fraction'].setText('.2');w.refresh()
                original=w.scenario()
                self.assertEqual((original.rows,original.columns),(4,5))
                w.preview.resize(400,300);w.preview.grab()
                preset=ScenarioPreset('Saved maze','',original)
                path=save_preset(preset,directory)
                w.dirty=False
                w.category_choice.setCurrentIndex(w.category_choice.findData('loops'))
                w._add_preset(load_preset(path),'Imported')
                self.assertEqual(w.current_category,'mazes')
                self.assertEqual(w.scenario(),original)
                with patch.object(w.process,'start') as start:
                    w.launch();start.assert_called_once()
                self.assertEqual(parse_preset(json.loads(w.pending_scenario)).scenario,original)
                w.maze_fields['rows'].setText('1');w.refresh()
                self.assertFalse(w.launch_button.isEnabled())
            finally:
                w.dirty=False;w.close();w.deleteLater();self.app.processEvents()
