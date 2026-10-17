"""Qt scenario editor with selectable presets and a managed MuJoCo process."""

import json
import os
from pathlib import Path
import sys
import uuid

from PySide6.QtCore import QProcess, Qt, QSettings
from PySide6.QtWidgets import (
    QApplication, QDoubleSpinBox, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QScrollArea,
)

from ..assets import EXAMPLES, example_for_path
from ..experiments import open_package
from ..scenarios.library import (BUNDLED_DIRECTORY, ScenarioPreset, discover_presets,
                      load_preset, save_preset, user_scenario_directory)
from .preview import TrackPreview
from ..scenarios import Corridor, Scenario, LoopScenario, Terrain, CIRCUITS


STYLE = """
QWidget { font-family: 'DejaVu Sans', sans-serif; font-size: 13px; color: #233b3b; }
QMainWindow { background: #f1f5f4; }
QFrame#card { background: white; border: 1px solid #dce6e2; border-radius: 12px; }
QLabel#heading { font-size: 25px; font-weight: 600; }
QLabel#section { font-size: 15px; font-weight: 600; }
QLabel#muted { color: #617773; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #f9fbfa; border: 1px solid #cbd9d3;
    border-radius: 6px; padding: 7px; min-height: 18px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #21816b; }
QComboBox QAbstractItemView { background: white; selection-background-color: #dceee7; }
QPushButton { background: #edf4f0; border: 1px solid #cbd9d3; border-radius: 6px; padding: 9px 14px; }
QPushButton:hover { background: #dcece4; }
QPushButton#primary { background: #176b56; color: white; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #125541; }
QPushButton:disabled { background: #e5eae7; color: #899990; }
QTableWidget { background: white; alternate-background-color: #f5f8f6; border: 1px solid #dce6e2;
    border-radius: 6px; gridline-color: #e8efeb; selection-background-color: #dceee7;
    selection-color: #233b3b; }
QHeaderView::section { background: #edf4f0; padding: 8px; border: none; font-weight: 600; }
QCheckBox { spacing: 8px; }
"""


def card(title):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(12)
    heading = QLabel(title)
    heading.setObjectName("section")
    layout.addWidget(heading)
    return frame, layout


class ScenarioWindow(QMainWindow):
    def __init__(self, library_directory=None):
        super().__init__()
        self.library_directory = Path(library_directory) if library_directory else user_scenario_directory()
        self.loading = self.dirty = self.stopping = False
        self.current_preset_index = -1
        self.current_category = "corridors"
        self.catalog = []
        self.loop_shape = "circle"
        self.last_run_directory = None
        self.last_error_output = ""
        self.setWindowTitle("Line tracker · Scenario studio")
        self.resize(1120, 820)
        self.setMinimumSize(930, 700)
        self.setStyleSheet(STYLE)
        central = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(central)
        self.setCentralWidget(scroll)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        title = QLabel("Scenario studio")
        title.setObjectName("heading")
        layout.addWidget(title)
        subtitle = QLabel("Choose a robot, shape a track, and run your experiment.")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)
        self.source_choice = QComboBox()
        self.source_choice.addItem("Built-in experiments / generated tracks", "generated")
        self.source_choice.addItem("Import MuJoCo scene XML", "scene")
        self.source_choice.addItem("Assignment / full experiment ZIP", "full")
        self.source_choice.addItem("Robot + controller ZIP on generated track", "robot")
        layout.addWidget(self.source_choice)
        self.scene_card, scene_layout = card("MuJoCo scene")
        layout.addWidget(self.scene_card)
        scene_row = QHBoxLayout()
        self.scene_path = QLineEdit()
        self.scene_path.setPlaceholderText("Select a complete scene.xml file")
        scene_row.addWidget(self.scene_path)
        scene_browse = QPushButton("Browse…")
        scene_browse.clicked.connect(self.browse_scene)
        scene_row.addWidget(scene_browse)
        scene_layout.addLayout(scene_row)
        scene_note = QLabel("Loads the complete scene, including any robots already in it. Keep its referenced assets "
                            "and includes in place. No additional robot or generated track is added. "
                            "Automatic line following is unavailable; use the viewer's actuator controls where provided.")
        scene_note.setWordWrap(True)
        scene_layout.addWidget(scene_note)
        self.scene_card.hide()
        self.package_card, package_layout = card("Experiment package")
        layout.addWidget(self.package_card)
        package_row = QHBoxLayout()
        self.package_path = QLineEdit()
        self.package_path.setPlaceholderText("Any ZIP containing python/main.py and scenes/, or experiment.json")
        package_row.addWidget(self.package_path)
        package_browse = QPushButton("Browse ZIP…")
        package_browse.clicked.connect(self.browse_package)
        package_row.addWidget(package_browse)
        package_layout.addLayout(package_row)
        dependency_row = QHBoxLayout()
        dependency_row.addWidget(QLabel("Menagerie (optional)"))
        self.menagerie_path = QLineEdit(str(QSettings("line-tracker-sim", "studio").value("menagerie", "")))
        dependency_row.addWidget(self.menagerie_path)
        dependency_browse = QPushButton("Choose folder…")
        dependency_browse.clicked.connect(self.browse_menagerie)
        dependency_row.addWidget(dependency_browse)
        package_layout.addLayout(dependency_row)
        package_note = QLabel("Assignment ZIPs run python/main.py directly; no JSON file is required. "
                              "Advanced packages can use experiment.json. "
                              "You will be asked to trust the Python code before it runs. "
                              "A full experiment supplies its own environment; robot packages use the track below.")
        package_note.setWordWrap(True)
        package_layout.addWidget(package_note)
        self.package_card.hide()
        columns = QHBoxLayout()
        columns.setSpacing(18)
        layout.addLayout(columns, 1)
        left, right = QVBoxLayout(), QVBoxLayout()
        columns.addLayout(left, 5)
        columns.addLayout(right, 6)

        robot_card, robot_layout = card("Robot")
        self.robot_card = robot_card
        left.addWidget(robot_card)
        self.robot_choice = QComboBox()
        for example in EXAMPLES:
            self.robot_choice.addItem(example.label, str(example.path))
        self.robot_choice.addItem("Custom MJCF model…", None)
        robot_layout.addWidget(self.robot_choice)
        robot_row = QHBoxLayout()
        self.robot_path = QLineEdit(str(EXAMPLES[0].path))
        self.robot_path.setAccessibleName("Robot XML path")
        self.robot_path.setToolTip("Keep referenced meshes and textures in their original folders.")
        robot_row.addWidget(self.robot_path)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse_robot)
        robot_row.addWidget(browse)
        robot_layout.addLayout(robot_row)
        self.auto_follow = QCheckBox("Automatically follow the line")
        self.auto_follow.setChecked(True)
        robot_layout.addWidget(self.auto_follow)
        self.robot_note = QLabel("Ideal geometric tracking · bundled robot controller")
        self.robot_note.setObjectName("muted")
        self.robot_note.setWordWrap(True)
        robot_layout.addWidget(self.robot_note)

        scenario_card, scenario_layout = card("Scenario")
        self.scenario_card = scenario_card
        left.addWidget(scenario_card, 1)
        self.category_choice = QComboBox()
        self.category_choice.addItem("Corridor tracks", "corridors")
        self.category_choice.addItem("Loop tracks", "loops")
        scenario_layout.addWidget(self.category_choice)
        self.preset_choice = QComboBox()
        scenario_layout.addWidget(self.preset_choice)
        self.description = QLabel()
        self.description.setObjectName("muted")
        self.description.setWordWrap(True)
        scenario_layout.addWidget(self.description)
        library_buttons = QHBoxLayout()
        import_button = QPushButton("Import JSON…")
        import_button.clicked.connect(self.import_scenario)
        self.save_button = QPushButton("Save to library…")
        self.save_button.clicked.connect(self.save_scenario)
        library_buttons.addWidget(import_button)
        library_buttons.addWidget(self.save_button)
        scenario_layout.addLayout(library_buttons)
        form = self.parameters_form = QFormLayout()
        self.count = QSpinBox()
        self.count.setRange(1, 100)
        self.width = QLineEdit("0.8")
        self.line_width = QLineEdit("0.025")
        self.radius = QLineEdit("2.0")
        form.addRow("Corridors", self.count)
        form.addRow("Radius / scale (m)", self.radius)
        form.addRow("Track width (m)", self.width)
        form.addRow("Line width (m)", self.line_width)
        scenario_layout.addLayout(form)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Length (m)", "Turn (°)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(150)
        scenario_layout.addWidget(self.table, 1)
        angles = self.angles = QLabel("Relative turns: + left, − right. First corridor faces +X.")
        angles.setWordWrap(True)
        angles.setObjectName("muted")
        scenario_layout.addWidget(angles)
        self.loop_note = QLabel("Closed circuit: automatic driving repeats laps until stopped.\n\n"
                                "The figure-eight has a flat crossing shared by both lobes.")
        self.loop_note.setWordWrap(True)
        self.loop_note.setObjectName("muted")
        scenario_layout.addWidget(self.loop_note)

        preview_card, preview_layout = card("Track preview")
        self.preview_card = preview_card
        right.addWidget(preview_card, 1)
        self.preview = TrackPreview()
        preview_layout.addWidget(self.preview, 1)
        self.summary = QLabel()
        self.summary.setObjectName("section")
        preview_layout.addWidget(self.summary)
        note = QLabel("Top view · schematic preview. MuJoCo opens in a separate window.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        preview_layout.addWidget(note)
        terrain_card, terrain_layout = card("Ground surface")
        self.terrain_card = terrain_card
        right.addWidget(terrain_card)
        terrain_form = QFormLayout()
        terrain_layout.addLayout(terrain_form)
        self.terrain_mode = QComboBox()
        for label, mode in (("Flat", "flat"), ("Smooth waves", "waves"), ("Random bumps", "random")):
            self.terrain_mode.addItem(label, mode)
        self.terrain_height = QDoubleSpinBox()
        self.terrain_height.setRange(0, 30)
        self.terrain_height.setSuffix(" cm")
        self.terrain_height.setSingleStep(0.5)
        self.terrain_spacing = QDoubleSpinBox()
        self.terrain_spacing.setRange(0.1, 10)
        self.terrain_spacing.setSuffix(" m")
        self.terrain_spacing.setSingleStep(0.1)
        self.terrain_resolution = QSpinBox()
        self.terrain_resolution.setRange(33, 513)
        self.terrain_seed = QSpinBox()
        self.terrain_seed.setRange(0, 2147483647)
        for label, widget in (("Surface", self.terrain_mode), ("Height variation", self.terrain_height),
                              ("Bump spacing", self.terrain_spacing), ("Grid resolution", self.terrain_resolution),
                              ("Random seed", self.terrain_seed)):
            terrain_form.addRow(label, widget)
        terrain_note = QLabel("0.3 cm is only 3 mm and looks almost flat. Try 5–10 cm to inspect the shape with automatic driving off. The start area stays level. Click Restart to apply changes.")
        terrain_note.setWordWrap(True)
        terrain_note.setObjectName("muted")
        terrain_layout.addWidget(terrain_note)
        self.terrain_mode.currentIndexChanged.connect(self._terrain_changed)
        for widget in (self.terrain_height, self.terrain_spacing, self.terrain_resolution, self.terrain_seed):
            widget.valueChanged.connect(self._edited)
        self.status = QLabel("Ready")
        self.status.setWordWrap(True)
        right.addWidget(self.status)
        self.launch_button = QPushButton("Open MuJoCo simulation")
        self.launch_button.setObjectName("primary")
        self.launch_button.clicked.connect(self.launch)
        right.addWidget(self.launch_button)
        self.stop_button = QPushButton("Stop simulation")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_simulation)
        right.addWidget(self.stop_button)

        self.process = QProcess(self)
        self.process.started.connect(self._send_scenario)
        self.process.readyReadStandardError.connect(self._read_errors)
        self.process.finished.connect(self._simulation_finished)
        self.process.errorOccurred.connect(self._process_error)
        self.robot_choice.currentIndexChanged.connect(self._robot_selected)
        self.robot_path.textChanged.connect(self._robot_changed)
        self.preset_choice.currentIndexChanged.connect(self._preset_selected)
        self.category_choice.currentIndexChanged.connect(self._category_selected)
        self.count.valueChanged.connect(self._resize_corridors)
        self.table.itemChanged.connect(self._edited)
        self.width.textChanged.connect(self._edited)
        self.line_width.textChanged.connect(self._edited)
        self.radius.textChanged.connect(self._edited)
        self.source_choice.currentIndexChanged.connect(self._source_changed)
        self.scene_path.textChanged.connect(self.refresh)
        self.package_path.textChanged.connect(self.refresh)
        errors = []
        self.loading = True
        for directory, label in ((BUNDLED_DIRECTORY, "Built-in"), (self.library_directory, "Saved")):
            entries, failures = discover_presets(directory)
            errors.extend(failures)
            for _, preset in entries:
                self.catalog.append((preset, label))
        self.loading = False
        self._fill_presets("corridors")
        if errors:
            self.status.setText("Some scenario files could not be loaded. Hover for details.")
            self.status.setToolTip("\n".join(errors))

    def browse_scene(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select MuJoCo scene", "", "MuJoCo XML (*.xml)")
        if path:
            self.scene_path.setText(path)

    def browse_package(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select experiment package", "", "Experiment ZIP (*.zip)")
        if path:
            self.package_path.setText(path)

    def browse_menagerie(self):
        path = QFileDialog.getExistingDirectory(self, "Select mujoco_menagerie directory", self.menagerie_path.text())
        if path:
            self.menagerie_path.setText(path)
            QSettings("line-tracker-sim", "studio").setValue("menagerie", path)

    def _source_changed(self, *_):
        source = self.source_choice.currentData()
        self.scene_card.setVisible(source == "scene")
        self.package_card.setVisible(source in ("full", "robot"))
        self.robot_card.setVisible(source == "generated")
        for widget in (self.scenario_card, self.preview_card, self.terrain_card):
            widget.setVisible(source in ("generated", "robot"))
        self.refresh()

    def _robot_selected(self, index):
        path = self.robot_choice.itemData(index)
        if path:
            self.robot_path.setText(path)
        else:
            self.browse_robot()
            self._robot_changed()

    def browse_robot(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select robot model", "", "MuJoCo XML (*.xml)")
        if path:
            self.robot_path.setText(path)

    def _robot_changed(self, *_):
        example = example_for_path(self.robot_path.text())
        self.robot_choice.blockSignals(True)
        self.robot_choice.setCurrentIndex(EXAMPLES.index(example) if example else len(EXAMPLES))
        self.robot_choice.blockSignals(False)
        self.auto_follow.setEnabled(example is not None)
        self.auto_follow.setChecked(example is not None)
        self.robot_note.setText("Ideal geometric tracking · bundled robot controller" if example else
                                "Custom model · manual controls. Start at the origin, facing +X, on z=0.")

    def _discard_edits(self):
        return not self.dirty or QMessageBox.question(
            self, "Unsaved scenario", "Discard unsaved scenario edits?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Discard

    def _category_selected(self, index):
        if self.loading:
            return
        if not self._discard_edits():
            self.category_choice.blockSignals(True)
            self.category_choice.setCurrentIndex(self.category_choice.findData(self.current_category))
            self.category_choice.blockSignals(False)
            return
        self._fill_presets(self.category_choice.itemData(index))

    def _fill_presets(self, category, selected=None):
        self.loading = True
        self.current_category = category
        self.category_choice.setCurrentIndex(self.category_choice.findData(category))
        self.preset_choice.clear()
        selected_index = 0
        for preset, label in self.catalog:
            if ("loops" if preset.scenario.closed else "corridors") == category:
                self.preset_choice.addItem(f"{preset.name} · {label}", preset)
                if preset is selected:
                    selected_index = self.preset_choice.count() - 1
        self.preset_choice.setCurrentIndex(selected_index)
        self.current_preset_index = self.preset_choice.currentIndex()
        self.loading = False
        if self.current_preset_index >= 0:
            self.apply_preset(self.preset_choice.currentData())
        else:
            scenario = LoopScenario() if category == "loops" else Scenario((Corridor(2),))
            self.apply_preset(ScenarioPreset("Custom track", "", scenario))

    def _preset_selected(self, index):
        if self.loading or index < 0:
            return
        if not self._discard_edits():
            self.preset_choice.blockSignals(True)
            self.preset_choice.setCurrentIndex(self.current_preset_index)
            self.preset_choice.blockSignals(False)
            return
        self.current_preset_index = index
        self.apply_preset(self.preset_choice.itemData(index))

    def apply_preset(self, preset):
        self.loading = True
        self.description.setText(preset.description)
        terrain = preset.scenario.terrain
        self.terrain_mode.setCurrentIndex(self.terrain_mode.findData(terrain.mode))
        self.terrain_height.setValue(terrain.height * 100)
        self.terrain_spacing.setValue(terrain.spacing)
        self.terrain_resolution.setValue(terrain.resolution)
        self.terrain_seed.setValue(terrain.seed)
        self._terrain_changed()
        closed = preset.scenario.closed
        self.parameters_form.setRowVisible(self.count, not closed)
        self.parameters_form.setRowVisible(self.radius, closed)
        self.table.setVisible(not closed)
        self.angles.setVisible(not closed)
        self.loop_note.setVisible(closed)
        self.width.setText(str(preset.scenario.width))
        self.line_width.setText(str(preset.scenario.line_width))
        if closed:
            self.loop_shape = preset.scenario.shape
            self.parameters_form.labelForField(self.radius).setText(
                CIRCUITS[self.loop_shape].size_label)
            self.radius.setText(str(preset.scenario.radius))
        else:
            self.count.setValue(len(preset.scenario.corridors))
            self.table.setRowCount(len(preset.scenario.corridors))
            for index, part in enumerate(preset.scenario.corridors):
                self._set_row(index, part.length, part.turn)
        self.loading = False
        self.dirty = False
        self.refresh()

    def _set_row(self, row, length, turn):
        self.table.setItem(row, 0, QTableWidgetItem(str(length)))
        item = QTableWidgetItem(str(turn) if row else "0")
        if row == 0:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 1, item)

    def _resize_corridors(self, count):
        if self.loading:
            return
        self.loading = True
        previous = self.table.rowCount()
        self.table.setRowCount(count)
        for row in range(previous, count):
            self._set_row(row, 2.0, 0.0)
        self.loading = False
        self._edited()

    def _terrain_changed(self, *_):
        mode = self.terrain_mode.currentData()
        for widget in (self.terrain_height, self.terrain_spacing, self.terrain_resolution):
            widget.setEnabled(mode != "flat")
        self.terrain_seed.setEnabled(mode == "random")
        self._edited()

    def scenario(self):
        terrain = Terrain(self.terrain_mode.currentData(), self.terrain_height.value()/100,
                          self.terrain_spacing.value(), self.terrain_resolution.value(), self.terrain_seed.value())
        if self.current_category == "loops":
            return LoopScenario(self.loop_shape, float(self.radius.text()),
                                float(self.width.text()), float(self.line_width.text()), terrain)
        return Scenario(tuple(Corridor(float(self.table.item(row, 0).text()),
                                        float(self.table.item(row, 1).text()))
                              for row in range(self.table.rowCount())),
                        float(self.width.text()), float(self.line_width.text()), terrain)

    def _edited(self, *_):
        if not self.loading:
            self.dirty = True
            self.refresh()

    def refresh(self):
        source = self.source_choice.currentData()
        if source in ("full", "robot"):
            valid = bool(self.package_path.text().strip()) and Path(self.package_path.text()).expanduser().is_file()
            error = "Select an experiment ZIP."
            if source == "robot":
                try:
                    selected = self.scenario()
                    self.preview.set_scenario(selected)
                    self.summary.setText(f"{'Closed loop' if selected.closed else 'Corridor track'} · {selected.total_length:.1f} m")
                except ValueError as exc:
                    valid, error = False, str(exc)
                    self.preview.set_scenario(None)
            running = self.process.state() != QProcess.ProcessState.NotRunning
            self.launch_button.setEnabled(valid)
            self.launch_button.setText("Restart experiment" if running else "Open experiment")
            self.status.setText("Package will be validated before approval and launch." if valid else error)
            self.save_button.setEnabled(source == "robot" and self.preview.scenario is not None)
            return
        if self.source_choice.currentData() == "scene":
            running = self.process.state() != QProcess.ProcessState.NotRunning
            valid = bool(self.scene_path.text().strip()) and Path(self.scene_path.text()).expanduser().is_file()
            self.launch_button.setEnabled(valid)
            self.launch_button.setText("Restart with imported scene" if running else "Open MuJoCo scene")
            self.status.setText("Click Restart to load the selected scene." if valid and running else
                                "Ready to load scene as supplied." if valid else "Select an existing MuJoCo scene XML.")
            return
        try:
            scenario = self.scenario()
        except ValueError as exc:
            self.preview.set_scenario(None)
            self.summary.setText("Check scenario parameters")
            self.status.setText(str(exc))
            self.launch_button.setEnabled(False)
            self.save_button.setEnabled(False)
            return
        self.preview.set_scenario(scenario)
        self.summary.setText(f"Closed loop · {scenario.total_length:.1f} m per lap · repeats" if scenario.closed else
                            f"{len(scenario.corridors)} corridors · {scenario.total_length:g} m total")
        running = self.process.state() != QProcess.ProcessState.NotRunning
        self.launch_button.setEnabled(True)
        self.launch_button.setText("Restart with selected scenario" if running else "Open MuJoCo simulation")
        self.save_button.setEnabled(True)
        self.status.setText("MuJoCo is running the previous launch. Click Restart to apply the selected scenario." if running else
                            "Edited scenario · save to library to keep your changes." if self.dirty else
                            "Ready to simulate")

    def import_scenario(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import scenario", "", "Scenario JSON (*.json)")
        if not path:
            return
        try:
            preset = load_preset(path)
            if self._discard_edits():
                self._add_preset(preset, "Imported")
                self.status.setText("Imported scenario · save to library to keep it between launches.")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Cannot import scenario", str(exc))

    def _add_preset(self, preset, origin):
        self.catalog.append((preset, origin))
        self._fill_presets("loops" if preset.scenario.closed else "corridors", selected=preset)

    def save_scenario(self):
        name, accepted = QInputDialog.getText(self, "Save scenario", "Scenario name:")
        if not accepted:
            return
        try:
            preset = ScenarioPreset(name.strip(), self.description.text(), self.scenario())
            path = save_preset(preset, self.library_directory)
            self._add_preset(preset, "Saved")
            self.status.setText(f"Saved to {path}")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Cannot save scenario", str(exc))

    def launch(self):
        try:
            run_directory = None
            source = self.source_choice.currentData()
            if source in ("full", "robot"):
                package_path = Path(self.package_path.text()).expanduser().resolve()
                with open_package(package_path, menagerie_directory=self.menagerie_path.text() or None) as experiment:
                    if experiment.mode != source and not (source == "full" and experiment.mode == "standalone"):
                        raise ValueError(f"This ZIP is a {experiment.mode} experiment. Select the matching source mode.")
                    if experiment.menagerie and not self.menagerie_path.text():
                        raise ValueError("This experiment requires your local mujoco_menagerie folder.")
                    pending_scenario = (json.dumps(ScenarioPreset("Simulation", "", self.scenario()).to_dict(),
                                                  allow_nan=False).encode("utf-8") if source == "robot" else b"")
                    answer = QMessageBox.question(
                        self, "Trust experiment controller?",
                        f"Run Python from '{experiment.name}'?\n\n"
                        f"Controller: {experiment.controller_path.relative_to(experiment.root)}\n"
                        f"ZIP SHA-256: {experiment.digest}\n\n"
                        "This code can access your files and network. It runs in a separate process, "
                        "which is not a security sandbox. Only run packages you trust.",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                        QMessageBox.StandardButton.Cancel)
                    if answer != QMessageBox.StandardButton.Yes:
                        return
                    arguments = ["-m", "robo_sim_py.simulation", "--package", str(package_path),
                                 "--approved-sha256", experiment.digest]
                    if experiment.mode == "standalone":
                        run_directory = user_scenario_directory().parent / "runs" / uuid.uuid4().hex
                        arguments.extend(["--run-directory", str(run_directory)])
                    if experiment.menagerie or (experiment.mode == "standalone" and self.menagerie_path.text()):
                        arguments.extend(["--menagerie", str(Path(self.menagerie_path.text()).expanduser().resolve())])
            elif source == "scene":
                scene_path = Path(self.scene_path.text()).expanduser().resolve()
                if not self.scene_path.text().strip() or not scene_path.is_file():
                    raise ValueError("Select an existing scene XML file.")
                arguments = ["-m", "robo_sim_py.simulation", "--scene", str(scene_path)]
                pending_scenario = b""
            else:
                preset = ScenarioPreset("Simulation", "", self.scenario())
                robot_path = Path(self.robot_path.text()).expanduser().resolve()
                if not robot_path.is_file():
                    raise ValueError("Select an existing robot XML file.")
                pending_scenario = json.dumps(preset.to_dict(), allow_nan=False).encode("utf-8")
                arguments = ["-m", "robo_sim_py.simulation", "--robot", str(robot_path)]
                if self.auto_follow.isChecked():
                    arguments.append("--auto-follow")
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Cannot start simulation", str(exc))
            return
        # Validate the replacement before stopping a working simulation.
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.stop_simulation()
            if self.process.state() != QProcess.ProcessState.NotRunning:
                self.status.setText("MuJoCo is still stopping. Try restarting again in a moment.")
                return
        self.last_run_directory = run_directory
        self.pending_scenario = pending_scenario
        executable = sys.executable
        if sys.platform == "darwin":
            executable = str(Path(sys.executable).with_name("mjpython"))
        self.process.setProgram(executable)
        self.process.setArguments(arguments)
        self.last_error_output = ""
        self.stopping = False
        self.launch_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("Opening MuJoCo…")
        self.process.start()

    def _send_scenario(self):
        self.process.write(self.pending_scenario)
        self.process.closeWriteChannel()
        self.refresh()

    def _read_errors(self):
        self.last_error_output = (self.last_error_output +
                                 bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace"))[-8000:]

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.stop_button.setEnabled(False)
            self.refresh()
            self.status.setText(f"Could not start MuJoCo: {self.process.errorString()}")

    def _simulation_finished(self, code, status):
        self._read_errors()
        self.stop_button.setEnabled(False)
        self.refresh()
        if self.last_run_directory and self.last_run_directory.is_dir():
            self.status.setText(f"Experiment files and outputs kept in {self.last_run_directory / 'assignment'}")
        if code != 0 and not self.stopping:
            QMessageBox.warning(self, "Simulation error", self.last_error_output or "MuJoCo closed unexpectedly.")

    def stop_simulation(self):
        self.stopping = True
        self.process.terminate()
        if not self.process.waitForFinished(1500):
            self.process.kill()
            self.process.waitForFinished(1500)

    def closeEvent(self, event):
        if not self._discard_edits():
            event.ignore()
            return
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.stop_simulation()
        event.accept()


def main():
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or os.environ.get("QT_QPA_PLATFORM")
    ):
        raise SystemExit("A desktop display is required to open the scenario editor.")
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ScenarioWindow()
    window.show()
    sys.exit(app.exec())
