"""Library-first contracts: interface parity, real physics, isolation, and errors."""
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import fields
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from navprobe import (ScenarioOptions, RunOptions, create_scenario, configure_scenario,
    generate_environment, export_scenario, validate_input, list_presets, list_robots,
    prepare_run, open_simulation, run_experiment, restart_simulation, load_preset)
from navprobe import cli


class LibraryServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()

    def test_every_cli_option_has_a_library_setting_or_operation(self):
        import argparse
        parser = cli.parser()
        commands = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        self.assertFalse(RunOptions().has_generation_settings())
        settings = {f.name for f in fields(RunOptions)}
        # These select explicit operations rather than describe a scenario/run.
        operations = {'help','command','kind','gui','save','output','path'}
        for command in commands.choices.values():
            for action in command._actions:
                self.assertIn(action.dest, settings | operations)

    def test_cli_and_python_layout_configuration_have_equal_results(self):
        for flags, options in (
            (['--corridor','4','0','--corridor','3','90','--width','1.2'],
             ScenarioOptions(corridor=((4,0),(3,90)),width=1.2)),
            (['--loop','figure_eight','--radius','3'], ScenarioOptions(loop='figure_eight',radius=3)),
            (['--dungeon','--rooms','4','--layout-seed','9'],ScenarioOptions(dungeon=True,rooms=4,layout_seed=9)),
            (['--maze','--maze-algorithm','growing-tree','--maze-rows','3','--maze-columns','4','--loop-fraction','.2'],
             ScenarioOptions(maze=True,maze_algorithm='growing-tree',maze_rows=3,maze_columns=4,loop_fraction=.2))):
            with self.subTest(flags=flags), redirect_stderr(io.StringIO()):
                via_cli=cli.selected_preset(cli.parser().parse_args(['scenario',*flags]))
                self.assertEqual(via_cli,create_scenario(options))
        with self.assertRaisesRegex(ValueError,'one scenario source'):
            create_scenario(maze=True,dungeon=True)
        with self.assertRaisesRegex(ValueError,'Maze settings'):
            create_scenario(maze_rows=4)
        for field in ('scenario', 'preset', 'scenic', 'loop', 'robot'):
            with self.assertRaises(ValueError): create_scenario(**{field: ''})
        for field in ('scene', 'package', 'robot'):
            with self.assertRaises(ValueError): prepare_run(**{field: ''})

    def test_generation_persistence_catalog_and_validation_are_silent(self):
        output=io.StringIO()
        with redirect_stdout(output),redirect_stderr(output):
            built=generate_environment(ScenarioOptions(maze=True,maze_rows=3,maze_columns=3),self.root/'scene.xml')
            self.assertTrue(built.path.is_file())
            self.assertEqual(validate_input(built.path).kind,'scene')
            preset=create_scenario(scenario=built.scenario,name='Python')
            saved=export_scenario(preset,self.root/'case.json')
            self.assertEqual(load_preset(saved),preset)
            self.assertEqual(validate_input(saved).name,'Python')
            (self.root/'broken.json').write_text('broken')
            listing=list_presets(self.root)
            self.assertTrue(any(e.preset.name=='Python' for e in listing.entries))
            self.assertEqual(len(listing.errors),1)
            self.assertTrue(list_robots())
        self.assertEqual(output.getvalue(),'')
        with self.assertRaises(FileExistsError):
            export_scenario(preset,saved)
        with self.assertRaises(ValueError):
            validate_input(self.root/'broken.json')

    def test_run_preparation_matches_cli_without_output_or_files(self):
        options=RunOptions(maze=True,maze_rows=3,maze_columns=3,navigation='astar',
                           grid_resolution=.2,navigation_clearance=.35,simulation_speed=5)
        output=io.StringIO()
        with redirect_stdout(output),redirect_stderr(output):
            request=prepare_run(options)
        self.assertEqual(output.getvalue(),'')
        args=cli.parser().parse_args(['run','--maze','--maze-rows','3','--maze-columns','3',
            '--navigation','astar','--grid-resolution','.2','--navigation-clearance','.35','--simulation-speed','5'])
        with redirect_stderr(io.StringIO()):
            self.assertEqual(request.worker_request(),cli.worker_request(args))
        self.assertEqual(list(self.root.iterdir()),[])
        with self.assertRaises(ValueError):
            prepare_run(scene=self.root/'scene.xml',maze=True)
        with self.assertRaises(ValueError):
            prepare_run(simulation_speed=float('nan'))

    def test_headless_real_physics_reset_cleanup_and_closed_session(self):
        before=set(self.root.iterdir())
        with open_simulation(corridor=((2,0),),navigation='line') as session:
            initial=session.data.qpos.copy()
            self.assertAlmostEqual(session.step(500).time,500*session.model.opt.timestep)
            self.assertGreater(session.data.qpos[0],initial[0]+.01)
            session.reset()
            self.assertEqual(session.data.time,0)
            for invalid in (0,-1,True,1.5):
                with self.assertRaises(ValueError):session.step(invalid)
        self.assertTrue(session.closed)
        with self.assertRaises(RuntimeError):session.step()
        self.assertEqual(set(self.root.iterdir()),before)

    def test_native_python_controller_lifecycle_without_a_zip(self):
        class Controller:
            def __init__(self):self.events=[]
            def reset(self,model,data,context):self.events.append(('reset',context.scenario))
            def step(self,model,data,context):self.events.append(('step',float(data.time)))
            def close(self):self.events.append(('close',None))
        controller=Controller()
        with open_simulation(auto_follow=False,controller=controller) as session:
            session.step(3)
            session.reset()
            self.assertIs(session.controller,controller)
        self.assertEqual([e[0] for e in controller.events],['reset','step','step','step','reset','close'])
        with self.assertRaises(ValueError):
            open_simulation(controller=controller)  # automatic bundled controller would conflict
        with self.assertRaisesRegex(ValueError,'boolean'):
            prepare_run(trust_package='false')

    def package(self, code, *, standalone=False):
        from test_experiments import make_zip
        path=make_zip(self.root/'robot.zip')
        if standalone:
            with zipfile.ZipFile(path,'w') as archive:
                archive.writestr('python/main.py',code)
                archive.writestr('scenes/scene.xml','<mujoco/>')
        else:
            # Replace controller code in a freshly written fixture without duplicate members.
            with zipfile.ZipFile(path) as archive:
                files={name:archive.read(name) for name in archive.namelist()}
            name=next(n for n in files if n.endswith('/python/controller.py')) if any(n.endswith('/python/controller.py') for n in files) else next(n for n in files if n.endswith('/python/main.py'))
            files[name]=code.encode()
            with zipfile.ZipFile(path,'w') as archive:
                for name,value in files.items():archive.writestr(name,value)
        return path

    def test_imported_controller_closes_before_files_removed_and_restores_import_path(self):
        code='''from pathlib import Path
class Controller:
 def reset(self,model,data,context): self.root=context.root
 def step(self,model,data,context): data.ctrl[:]=0
 def close(self):
  assert self.root.exists()
  Path(self.root/'closed.txt').write_text('yes')
def create_controller(): return Controller()
'''
        path=self.package(code)
        result=validate_input(path)
        self.assertEqual(result.mode,'robot')
        old_path=sys.path[:]
        with self.assertRaisesRegex(ValueError,'trust_package'):
            prepare_run(package=path)
        with open_simulation(package=path,trust_package=True) as session:
            root=session.context.root
            self.assertTrue(root.exists())
            session.step(5)
        self.assertFalse(root.exists())
        self.assertEqual(sys.path,old_path)
        self.assertFalse(any(n.startswith('navprobe_controller_') and str(root) in str(getattr(m,'__file__','')) for n,m in sys.modules.items()))

    def test_imported_process_exit_becomes_an_exception_and_cleans_up(self):
        path=self.package('raise SystemExit(7)')
        old=sys.path[:]
        with self.assertRaisesRegex(RuntimeError,'process exit'):
            open_simulation(package=path,trust_package=True)
        self.assertEqual(old,sys.path)

    def test_standalone_script_exit_does_not_exit_host_and_requires_explicit_execution(self):
        path=self.package('raise SystemExit(4)',standalone=True)
        request=prepare_run(package=path,trust_package=True,run_directory=self.root/'outputs')
        self.assertFalse((self.root/'outputs').exists())
        with self.assertRaisesRegex(ValueError,'Standalone'):
            open_simulation(request)
        with self.assertRaisesRegex(RuntimeError,'status 4'):
            run_experiment(request)
        self.assertTrue((self.root/'outputs/experiment').is_dir())

    def test_restart_validates_before_stopping_a_working_simulation(self):
        with patch('navprobe.execution.stop_simulation') as stop:
            with self.assertRaises(ValueError):
                restart_simulation(object(),simulation_speed=-1)
            stop.assert_not_called()
