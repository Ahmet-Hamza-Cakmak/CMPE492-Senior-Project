"""Public branding, compatibility, and helpful optional-GUI behaviour."""
from contextlib import redirect_stderr, redirect_stdout
import io
import unittest
from unittest.mock import patch

import navprobe
import robo_sim_py
from robo_sim_py import cli


class PackagingInterfaceTests(unittest.TestCase):
    def test_new_scenario_namespace_keeps_class_identity(self):
        for name in ('Corridor','Scenario','LoopScenario','Terrain','DungeonScenario','MazeScenario'):
            self.assertIs(getattr(navprobe,name),getattr(robo_sim_py,name))
        self.assertEqual(navprobe.__version__,'0.1.0')
        self.assertEqual(cli.parser().prog,'navprobe')

    def test_gui_and_preview_explain_missing_extra(self):
        for arguments in (['--gui'],['preview','--corridor','3','0']):
            with self.subTest(arguments=arguments):
                output=io.StringIO()
                with patch('importlib.util.find_spec',return_value=None), redirect_stdout(output), redirect_stderr(output):
                    self.assertEqual(cli.main(arguments),1)
                self.assertIn('navprobe[gui]',output.getvalue())
                self.assertNotIn('Traceback',output.getvalue())
