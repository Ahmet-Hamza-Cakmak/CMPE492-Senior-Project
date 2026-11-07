"""Collision-free global planning and physical differential-drive execution."""

from contextlib import redirect_stderr
import importlib.util
import io
import itertools
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import mujoco
from shapely.geometry import box, LineString
from shapely.ops import unary_union

from robo_sim_py import DungeonScenario, Corridor, Scenario
from robo_sim_py.assets import create_controller, controller_mode
from robo_sim_py.navigation import astar, plan_dungeon
from robo_sim_py.scenarios.objects import StaticObjectSettings
from robo_sim_py.scenarios.dungeon_population import populate_dungeon, dungeon_objects
from robo_sim_py.scenarios.dungeon import dungeon_layout
from robo_sim_py.simulation import build_model, example_robot, run
from robo_sim_py import cli


class PlannerTests(unittest.TestCase):
    def test_detour_and_shortcuts_cover_inflated_free_space(self):
        floor=box(0,0,10,10);obstacle=box(4,2,6,8)
        planned=astar(floor,[obstacle],(1,5),(9,5),resolution=.25,clearance=.3)
        free=floor.buffer(-.3).difference(obstacle.buffer(.3))
        self.assertGreater(planned.length,8)
        self.assertEqual(planned.points[0],(1,5))
        self.assertEqual(planned.points[-1],(9,5))
        for a,b in zip(planned.points,planned.points[1:]):
            self.assertTrue(free.covers(LineString((a,b))))
        self.assertEqual(planned,astar(floor,[obstacle],(1,5),(9,5),resolution=.25,clearance=.3))

    def test_unreachable_invalid_and_bounded_search(self):
        with self.assertRaisesRegex(ValueError,'No start-to-goal'):
            astar(box(0,0,10,10),[box(4,0,6,10)],(1,5),(9,5))
        with self.assertRaisesRegex(ValueError,'budget'):
            astar(box(0,0,10,10),[box(4,2,6,8)],(1,5),(9,5),max_nodes=1)
        for options in ({'resolution':0},{'clearance':float('nan')}):
            with self.assertRaises(ValueError):
                astar(box(0,0,10,10),[],(1,1),(9,9),**options)
        with self.assertRaises(ValueError):
            plan_dungeon(Scenario((Corridor(2),)))
        with self.assertRaises(ValueError):
            plan_dungeon(DungeonScenario(),clearance=.1)

    def test_automatic_selection_and_explicit_baseline(self):
        self.assertEqual(controller_mode(example_robot(),DungeonScenario()),'astar')
        self.assertEqual(controller_mode(example_robot(),DungeonScenario(),'line'),'line')
        self.assertEqual(controller_mode(example_robot(),Scenario((Corridor(2),))),'line')
        with self.assertRaises(ValueError):
            controller_mode(example_robot('google_robot'),DungeonScenario(),'astar')

    def test_cli_navigation_and_playback_validation(self):
        args=cli.parser().parse_args(['run','--dungeon','--navigation','astar','--simulation-speed','5'])
        command,payload=cli.worker_request(args)
        self.assertEqual(command[command.index('--simulation-speed')+1],'5.0')
        self.assertIn('astar',command)
        for flags in (['--simulation-speed','0'],
                      ['--dungeon','--navigation','astar','--robot','google_robot'],
                      ['--dungeon','--navigation','astar','--no-auto-follow'],
                      ['--dungeon','--navigation-clearance','.1']):
            with self.subTest(flags=flags),self.assertRaises(ValueError):
                cli.worker_request(cli.parser().parse_args(['run',*flags]))

    def test_worker_options_and_blue_overlay(self):
        import json
        from robo_sim_py.simulation.__main__ import main
        from robo_sim_py.scenarios.library import ScenarioPreset
        from robo_sim_py.navigation import draw_route, PlannedRoute
        scenario=DungeonScenario()
        with patch('sys.argv',['worker','--robot',str(example_robot()),'--auto-follow','--navigation','astar',
                               '--grid-resolution','.2','--navigation-clearance','.35','--simulation-speed','5']), \
             patch('sys.stdin',io.StringIO(json.dumps(ScenarioPreset('Test','',scenario).to_dict()))), \
             patch('robo_sim_py.simulation.__main__.build_model') as build, \
             patch('robo_sim_py.simulation.__main__.run') as runner:
            self.assertEqual(main(),0)
            self.assertEqual(runner.call_args.kwargs['navigation'],'astar')
            self.assertEqual(runner.call_args.kwargs['simulation_speed'],5)
        model=mujoco.MjModel.from_xml_string('<mujoco/>')
        scene=mujoco.MjvScene(model,maxgeom=10)
        draw_route(scene,PlannedRoute(((0,0),(1,1)),math.sqrt(2),0,.25))
        self.assertEqual(scene.ngeom,1)
        self.assertEqual(model.ngeom,0)

    def test_playback_keeps_step_count_and_controller_updates(self):
        scenario=Scenario((Corridor(2),))
        model=build_model(example_robot(),scenario)
        sleep_budgets=[]
        for speed in (1,5):
            managed=SimpleNamespace(reset=Mock(),step=Mock(),close=Mock())
            viewer=SimpleNamespace(cam=mujoco.MjvCamera(),is_running=Mock(side_effect=[True]*5+[False]),sync=Mock())
            ticks=itertools.count(0,.000001)
            with patch('mujoco.viewer.launch_passive') as launch, \
                 patch('robo_sim_py.simulation.time.monotonic',side_effect=lambda:next(ticks)), \
                 patch('robo_sim_py.simulation.time.sleep') as sleep, \
                 patch('mujoco.mj_step',wraps=mujoco.mj_step) as step:
                launch.return_value.__enter__.return_value=viewer
                run(model,scenario,controller=managed,context=object(),simulation_speed=speed)
            self.assertEqual(step.call_count,5)
            self.assertEqual(managed.step.call_count,5)
            managed.close.assert_called_once()
            self.assertAlmostEqual(model.opt.timestep,.002)
            sleep_budgets.append(sum(call.args[0] for call in sleep.call_args_list))
        self.assertLess(sleep_budgets[1],sleep_budgets[0]/4)


@unittest.skipUnless(importlib.util.find_spec('scenic'),'Requires Scenic for populated cases')
class PhysicalNavigationTests(unittest.TestCase):
    def test_simple_robot_finishes_without_wall_or_box_contacts(self):
        for shape,seed in (('rectangular',7),('circular',12)):
            with self.subTest(shape=shape):
                scenario=populate_dungeon(DungeonScenario(map_width=12,map_height=8,room_min=3,room_max=4,
                    room_count=3,width=1.6,room_shape=shape,objects=StaticObjectSettings(count=3,seed=seed)))
                model=build_model(example_robot(),scenario);data=mujoco.MjData(model);mujoco.mj_forward(model,data)
                controller=create_controller(example_robot(),model,scenario)
                self.assertAlmostEqual(controller.speed,.16)
                free=dungeon_layout(scenario).floor.buffer(-.3).difference(
                    unary_union([o.footprint() for o in dungeon_objects(scenario)]).buffer(.3))
                for a,b in zip(controller.points,controller.points[1:]):
                    self.assertTrue(free.covers(LineString((a,b))))
                blocked={i for i in range(model.ngeom) if (mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_GEOM,i) or '').startswith(('static_box','corridor_wall'))}
                limit=int((controller.plan.length/.07+20)/model.opt.timestep)
                for _ in range(limit):
                    controller.update(data);mujoco.mj_step(model,data)
                    self.assertFalse(controller.lost)
                    self.assertFalse(any(any(int(g) in blocked for g in contact.geom) for contact in data.contact))
                    if controller.finished:break
                self.assertTrue(controller.finished,str(data.qpos[:2]))
                # The same immutable environment yields the same route on reset.
                self.assertEqual(controller.points,create_controller(example_robot(),model,scenario).points)
