"""CLI workflows without opening interactive graphics or executing imported Python."""

from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from robo_sim_py import cli
from robo_sim_py.scenarios.library import load_preset


class CliTests(unittest.TestCase):
    def invoke(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            code = cli.main(list(arguments))
        return code, output.getvalue()

    def test_no_arguments_print_help_without_tty(self):
        with patch.object(cli.sys.stdin, 'isatty', return_value=False):
            code, output = self.invoke()
        self.assertEqual(code, 0)
        self.assertIn('--gui', output)

    def test_gui_is_explicit_and_gets_clean_arguments(self):
        with patch('robo_sim_py.ui.editor.main') as gui:
            self.assertEqual(self.invoke('--gui')[0], 0)
            gui.assert_called_once_with(['robo-sim-py'])

    def test_edit_export_import_and_save_loop(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'loop.json'
            library = Path(directory) / 'library'
            code, message = self.invoke('scenario', '--loop', 'figure_eight', '--radius', '3',
                                        '--terrain', 'random', '--height', '.01', '--seed', '7',
                                        '--name', 'Experiment', '--output', str(output),
                                        '--save', '--library', str(library))
            self.assertEqual(code, 0, message)
            preset = load_preset(output)
            self.assertEqual(preset.scenario.terrain.seed, 7)
            self.assertEqual(preset.scenario.radius, 3)
            self.assertEqual(len(list(library.glob('*.json'))), 1)
            self.assertEqual(self.invoke('validate', str(output))[0], 0)
            self.assertIn('Experiment', self.invoke('list', 'presets', '--library', str(library))[1])
            # Never silently overwrite scenario exports.
            self.assertEqual(self.invoke('scenario', '--output', str(output))[0], 1)

    def test_corridor_editing_and_invalid_parameters(self):
        code, output = self.invoke('scenario', '--corridor', '2', '0', '--corridor', '1', '-90', '--width', '1')
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload['corridors'][1]['turn'], -90)
        for options in (['--width', '-1'], ['--radius', '3'], ['--corridor', '2', '90']):
            self.assertEqual(self.invoke('scenario', *options)[0], 1)

    def test_registered_and_custom_robot_controller_selection(self):
        args = cli.parser().parse_args(['run', '--preset', '05_circle'])
        command, payload = cli.worker_request(args)
        self.assertIn('--auto-follow', command)
        self.assertEqual(json.loads(payload)['type'], 'loop')
        with tempfile.TemporaryDirectory() as directory:
            robot = Path(directory) / 'robot.xml'
            robot.write_text('<mujoco/>')
            args = cli.parser().parse_args(['run', '--robot', str(robot)])
            self.assertNotIn('--auto-follow', cli.worker_request(args)[0])
            args.auto_follow = True
            with self.assertRaises(ValueError):
                cli.worker_request(args)

    def test_scene_rejects_track_options_and_launches_without_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            scene = Path(directory) / 'scene.xml'
            scene.write_text('<mujoco/>')
            args = cli.parser().parse_args(['run', '--scene', str(scene)])
            self.assertEqual(cli.worker_request(args)[1], b'')
            args.width = 1
            with self.assertRaises(ValueError):
                cli.worker_request(args)

    def test_package_requires_trust_and_passes_digest(self):
        package = Mock(mode='robot', menagerie=False, digest='abc123')
        package.name = 'Demo'
        with patch('robo_sim_py.experiments.open_package') as opened:
            opened.return_value.__enter__.return_value = package
            args = cli.parser().parse_args(['run', '--package', 'demo.zip'])
            with self.assertRaisesRegex(ValueError, 'trust-package'):
                cli.worker_request(args)
            args.trust_package = True
            command, payload = cli.worker_request(args)
            self.assertIn('abc123', command)
            self.assertEqual(json.loads(payload)['version'], 1)
            package.mode = 'full'
            args.width = 1
            with self.assertRaises(ValueError):
                cli.worker_request(args)

    def test_shell_replacement_validated_before_stop(self):
        shell = cli.SimulationShell()
        shell.process = Mock()
        with patch.object(cli, 'stop_worker') as stop, redirect_stderr(io.StringIO()):
            shell.default('run --robot /missing/robot.xml')
            stop.assert_not_called()
        with patch.object(cli, 'start_worker') as start, patch.object(cli, 'stop_worker') as stop, redirect_stdout(io.StringIO()):
            shell.default('run')
            stop.assert_called_once()
            start.assert_called_once()
            shell.do_restart('')
            self.assertEqual(start.call_count, 2)
            shell.do_stop('')

    def test_worker_failure_is_returned(self):
        with patch.object(cli, 'start_worker') as start:
            start.return_value.wait.return_value = 1
            self.assertEqual(self.invoke('run')[0], 1)

    def test_preview_uses_same_scenario(self):
        with patch.object(cli, 'preview', return_value=0) as preview:
            self.assertEqual(self.invoke('preview', '--loop', 'circle', '--radius', '4')[0], 0)
            self.assertEqual(preview.call_args.args[0].scenario.radius, 4)
