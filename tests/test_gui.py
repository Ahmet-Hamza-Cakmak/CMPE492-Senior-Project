import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QProcess, Qt
from PySide6.QtTest import QTest

from robo_sim_py.ui.editor import ScenarioWindow
from robo_sim_py.scenarios.library import discover_presets


class EditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.window = ScenarioWindow(self.directory.name)

    def tearDown(self):
        self.window.dirty = False
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def test_assignment_zip_without_manifest_launches_as_script(self):
        from zipfile import ZipFile
        archive_path = Path(self.directory.name) / "whatever.zip"
        with ZipFile(archive_path, 'w') as archive:
            archive.writestr("arbitrary/python/main.py", "raise RuntimeError('Do not execute in editor')")
            archive.writestr("arbitrary/scenes/circuit.xml", "<mujoco/>")
        self.window.source_choice.setCurrentIndex(self.window.source_choice.findData("full"))
        self.window.package_path.setText(str(archive_path))
        self.window.menagerie_path.setText("")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
             patch.object(self.window.process, "start") as start:
            self.window.launch()
            start.assert_called_once()
        self.assertIn("--run-directory", self.window.process.arguments())
        self.assertEqual(self.window.pending_scenario, b"")
        self.assertIsNotNone(self.window.last_run_directory)

    def test_package_approval_payload_and_switching(self):
        from test_experiments import make_zip
        package = make_zip(Path(self.directory.name) / "robot.zip")
        self.window.source_choice.setCurrentIndex(self.window.source_choice.findData("robot"))
        self.window.package_path.setText(str(package))
        self.assertTrue(self.window.robot_card.isHidden())
        self.assertFalse(self.window.scenario_card.isHidden())
        self.window.terrain_mode.setCurrentIndex(1)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel), \
             patch.object(self.window.process, "start") as start:
            self.window.launch()
            start.assert_not_called()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
             patch.object(self.window.process, "start") as start:
            self.window.launch()
            start.assert_called_once()
        self.assertIn("--package", self.window.process.arguments())
        self.assertIn("--approved-sha256", self.window.process.arguments())
        self.assertNotIn("--auto-follow", self.window.process.arguments())
        self.assertEqual(json.loads(self.window.pending_scenario)["terrain"]["mode"], "waves")
        self.window.source_choice.setCurrentIndex(self.window.source_choice.findData("full"))
        with patch.object(QMessageBox, "warning") as warning, \
             patch.object(QMessageBox, "question") as question, \
             patch.object(self.window.process, "start") as start:
            self.window.launch()
            warning.assert_called_once()
            question.assert_not_called()
            start.assert_not_called()
        make_zip(package, "full")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
             patch.object(self.window.process, "start"):
            self.window.launch()
        self.assertEqual(self.window.pending_scenario, b"")
        self.window.source_choice.setCurrentIndex(0)
        self.assertEqual(self.window.scenario().terrain.mode, "waves")
        self.assertFalse(self.window.robot_card.isHidden())

    def test_imported_scene_mode_and_return_to_generated(self):
        original = self.window.scenario()
        self.window.source_choice.setCurrentIndex(1)
        self.assertFalse(self.window.launch_button.isEnabled())
        self.assertTrue(self.window.robot_card.isHidden())
        scene = Path(self.directory.name) / "scene.xml"
        scene.write_text('<mujoco><worldbody><geom type="plane" size="2 2 .1"/></worldbody></mujoco>')
        self.window.scene_path.setText(str(scene))
        self.assertTrue(self.window.launch_button.isEnabled())
        with patch.object(self.window.process, "start"):
            self.window.launch()
        self.assertIn("--scene", self.window.process.arguments())
        self.assertNotIn("--auto-follow", self.window.process.arguments())
        self.assertNotIn("--robot", self.window.process.arguments())
        self.assertEqual(self.window.pending_scenario, b"")
        self.window.source_choice.setCurrentIndex(0)
        self.assertFalse(self.window.robot_card.isHidden())
        self.assertEqual(self.window.scenario(), original)
        with patch.object(self.window.process, "start"):
            self.window.launch()
        self.assertIn("--robot", self.window.process.arguments())
        self.assertIn("--auto-follow", self.window.process.arguments())

    def test_select_edit_validate_and_preserve_edits_on_cancel(self):
        self.window.preset_choice.setCurrentIndex(1)
        self.assertEqual(self.window.scenario().corridors[1].turn, 90)
        self.window.table.item(1, 0).setText("3.5")
        self.assertEqual(self.window.preview.scenario.corridors[1].length, 3.5)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            self.window.preset_choice.setCurrentIndex(2)
        self.assertEqual(self.window.preset_choice.currentIndex(), 1)
        self.assertEqual(self.window.scenario().corridors[1].length, 3.5)
        self.window.width.setText("invalid")
        self.assertFalse(self.window.launch_button.isEnabled())
        self.assertFalse(self.window.save_button.isEnabled())
        self.assertIsNone(self.window.preview.scenario)
        self.window.width.setText("0.8")
        self.assertTrue(self.window.launch_button.isEnabled())
        self.window.count.setValue(3)
        self.assertEqual(self.window.scenario().corridors[1].length, 3.5)
        self.assertEqual(len(self.window.scenario().corridors), 3)

    def test_save_and_discover_in_next_session(self):
        self.window.terrain_mode.setCurrentIndex(2)
        self.window.terrain_height.setValue(2.5)
        self.window.terrain_seed.setValue(17)
        self.assertTrue(self.window.terrain_seed.isEnabled())
        self.window.count.setValue(3)
        self.window.table.item(1, 1).setText("-45")
        expected = self.window.scenario()
        with patch.object(self.window.process, "start"):
            self.window.launch()
        self.assertEqual(json.loads(self.window.pending_scenario)["terrain"]["seed"], 17)
        with patch("robo_sim_py.ui.editor.QInputDialog.getText", return_value=("My experiment", True)):
            self.window.save_scenario()
        entries, errors = discover_presets(self.directory.name)
        self.assertFalse(errors)
        self.assertEqual(entries[0][1].scenario, expected)
        reopened = ScenarioWindow(self.directory.name)
        try:
            reopened.preset_choice.setCurrentIndex(reopened.preset_choice.count() - 1)
            self.assertEqual(reopened.scenario(), expected)
        finally:
            reopened.close()

    def test_custom_model_disables_controller_and_launch_snapshot_is_current(self):
        self.window.robot_choice.setCurrentIndex(1)
        self.window.preset_choice.setCurrentIndex(3)
        self.assertTrue(self.window.auto_follow.isChecked())
        with patch.object(self.window.process, "start"):
            self.window.launch()
        self.assertIn("--auto-follow", self.window.process.arguments())
        self.assertEqual(json.loads(self.window.pending_scenario)["corridors"][2]["turn"], -90)
        custom = Path(self.directory.name) / "robot.xml"
        custom.write_text("<mujoco/>")
        self.window.robot_path.setText(str(custom))
        self.assertFalse(self.window.auto_follow.isEnabled())
        with patch.object(self.window.process, "start"):
            self.window.launch()
        self.assertNotIn("--auto-follow", self.window.process.arguments())

    def test_worker_error_returns_to_editor(self):
        custom = Path(self.directory.name) / "broken.xml"
        custom.write_text("not valid XML")
        self.window.robot_path.setText(str(custom))
        with patch.object(QMessageBox, "warning") as warning:
            self.window.launch()
            self.assertTrue(self.window.process.waitForFinished(10000))
            self.app.processEvents()
            self.assertNotEqual(self.window.process.exitCode(), 0)
            self.assertIn("Cannot run simulation", self.window.last_error_output)
            warning.assert_called_once()
        self.assertTrue(self.window.launch_button.isEnabled())
        self.assertFalse(self.window.stop_button.isEnabled())

    def test_loop_category_edit_save_reload_and_switch_back(self):
        self.assertEqual(self.window.preset_choice.count(), 4)
        self.window.category_choice.setCurrentIndex(1)
        self.assertEqual(self.window.preset_choice.count(), 2)
        self.assertTrue(self.window.scenario().closed)
        self.assertTrue(self.window.table.isHidden())
        self.window.preset_choice.setCurrentIndex(1)
        self.assertEqual(self.window.scenario().shape, "figure_eight")
        self.window.radius.setText("4")
        with patch("robo_sim_py.ui.editor.QInputDialog.getText", return_value=("Large eight", True)):
            self.window.save_scenario()
        with patch.object(self.window.process, "start"):
            self.window.launch()
        self.assertEqual(json.loads(self.window.pending_scenario)["type"], "loop")
        reopened = ScenarioWindow(self.directory.name)
        try:
            reopened.category_choice.setCurrentIndex(1)
            reopened.preset_choice.setCurrentIndex(2)
            self.assertEqual(reopened.scenario().radius, 4)
            reopened.category_choice.setCurrentIndex(0)
            self.assertFalse(reopened.scenario().closed)
            self.assertFalse(reopened.table.isHidden())
            self.assertEqual(reopened.preset_choice.count(), 4)
        finally:
            reopened.close()

    def test_keyboard_switching_updates_preview_and_launch_payload(self):
        self.window.show()
        for index in (1, 2, 3, 0, 3, 1):
            self.window.preset_choice.setFocus()
            QTest.keyClick(self.window.preset_choice, Qt.Key.Key_Home)
            for _ in range(index):
                QTest.keyClick(self.window.preset_choice, Qt.Key.Key_Down)
            self.app.processEvents()
            expected = self.window.preset_choice.itemData(index)
            self.assertEqual(self.window.preview.scenario, expected.scenario)
            with patch.object(self.window.process, "start"):
                self.window.launch()
            self.assertEqual(json.loads(self.window.pending_scenario)["corridors"],
                             expected.to_dict()["corridors"])

    def test_switch_running_scenario_and_restart_sends_new_geometry(self):
        # Real worker processes exercise pipe reuse and stop/restart sequencing
        # without needing a display for MuJoCo's interactive viewer.
        original_start = self.window.process.start
        results = []

        def start_headless_worker():
            output = Path(self.directory.name) / f"run-{len(results)}.json"
            results.append(output)
            script = (
                "import json,sys,time; from pathlib import Path; "
                "from robo_sim_py import Scenario,Corridor; "
                "p=json.load(sys.stdin); s=Scenario(tuple(Corridor(**c) for c in p['corridors'])); "
                "Path(sys.argv[1]).write_text(json.dumps(s.points())); time.sleep(20)"
            )
            self.window.process.setArguments(["-c", script, str(output)])
            original_start()

        def wait_for_output(path):
            deadline = time.monotonic() + 5
            while not path.exists() and time.monotonic() < deadline:
                QTest.qWait(10)
            self.assertTrue(path.exists())
            return json.loads(path.read_text())

        with patch.object(self.window.process, "start", side_effect=start_headless_worker), \
             patch.object(QMessageBox, "warning") as warning:
            self.window.launch()
            first = wait_for_output(results[0])
            self.window.preset_choice.setCurrentIndex(2)
            self.assertEqual(self.window.process.state(), QProcess.ProcessState.Running)
            self.assertTrue(self.window.launch_button.isEnabled())
            self.assertIn("Restart", self.window.launch_button.text())
            self.window.launch()
            second = wait_for_output(results[1])
            self.assertNotEqual(first, second)
            self.assertEqual(second[-1], [2.0, -2.0])
            self.window.stop_simulation()
            self.assertEqual(self.window.process.state(), QProcess.ProcessState.NotRunning)
            self.assertTrue(self.window.launch_button.isEnabled())
            warning.assert_not_called()
