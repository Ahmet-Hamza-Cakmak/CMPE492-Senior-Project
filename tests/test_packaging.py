"""Public branding, compatibility, and helpful optional-GUI behaviour."""
from contextlib import redirect_stderr, redirect_stdout
from importlib.metadata import version
import io
import unittest
from unittest.mock import patch

import navprobe
from navprobe import scenarios
from navprobe import cli


class PackagingInterfaceTests(unittest.TestCase):
    def test_scenario_namespace_uses_navprobe_implementation(self):
        for name in ('Corridor','Scenario','LoopScenario','Terrain','DungeonScenario','MazeScenario'):
            self.assertIs(getattr(navprobe,name),getattr(scenarios,name))
        self.assertTrue(navprobe.MazeScenario.__module__.startswith('navprobe.'))
        self.assertEqual(navprobe.__version__, version('navprobe'))
        self.assertEqual(cli.parser().prog,'navprobe')

    def test_gui_and_preview_explain_missing_extra(self):
        for arguments in (['--gui'],['preview','--corridor','3','0']):
            with self.subTest(arguments=arguments):
                output=io.StringIO()
                with patch('importlib.util.find_spec',return_value=None), redirect_stdout(output), redirect_stderr(output):
                    self.assertEqual(cli.main(arguments),1)
                self.assertIn('navprobe[gui]',output.getvalue())
                self.assertNotIn('Traceback',output.getvalue())
