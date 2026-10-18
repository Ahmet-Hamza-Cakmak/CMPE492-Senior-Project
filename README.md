# Line tracker simulation

A Python package with a PySide6 desktop editor for MuJoCo robot experiments: generated circuits, imported scenes, and A2-style ZIP packages containing robots and Python controllers.

## Project organization

Application code is grouped by responsibility under [src/robo_sim_py/](src/robo_sim_py/):

| Area | What belongs here |
| --- | --- |
| [ui/](src/robo_sim_py/ui/) | [editor.py](src/robo_sim_py/ui/editor.py) contains the PySide6 window and process controls; [preview.py](src/robo_sim_py/ui/preview.py) draws the track preview. |
| [scenarios/](src/robo_sim_py/scenarios/) | [__init__.py](src/robo_sim_py/scenarios/__init__.py) defines corridor and loop geometry; [library.py](src/robo_sim_py/scenarios/library.py) loads/saves scenarios; [presets/](src/robo_sim_py/scenarios/presets/) holds the six built-in JSON configurations. |
| [simulation/](src/robo_sim_py/simulation/) | [__init__.py](src/robo_sim_py/simulation/__init__.py) builds and runs MuJoCo models; [walls.py](src/robo_sim_py/simulation/walls.py) calculates wall geometry; [__main__.py](src/robo_sim_py/simulation/__main__.py) is the separate viewer process entry point. |
| [assets/](src/robo_sim_py/assets/) | [__init__.py](src/robo_sim_py/assets/__init__.py) registers robot examples; [tracking.py](src/robo_sim_py/assets/tracking.py) provides shared driving logic. Each robot folder keeps its controller, XML, and supporting assets together. |
| [experiments/](src/robo_sim_py/experiments/) | Validates ZIP packages and manifests; defines the controller context, lifecycle and robot placement. |
| [tests/](tests/) | Geometry, driving, UI, persistence, and worker-process regression tests. |

The package's [__main__.py](src/robo_sim_py/__main__.py) is intentionally small: it starts the terminal interface; `--gui` opens the editor. Small robot controller files are also intentional—they configure shared tracking logic rather than duplicate it. Package marker files establish Python import boundaries.

To change the UI, start in the UI folder. To add a preset, add JSON in the preset folder. To add a robot, create its asset folder and register it in the asset registry. To change physics or walls, use the simulation folder.

The public imports `from robo_sim_py import Corridor, Scenario, LoopScenario` and `from robo_sim_py.simulation import build_model, example_robot, run` remain unchanged. Internal imports moved to their corresponding areas; the old flat modules are removed. User-saved scenarios remain in the same application-data directory and require no migration.

## Install and run

Requires Python 3.10 or newer and a desktop with OpenGL support.

```bash
python -m pip install "git+https://github.com/Ahmet-Hamza-Cakmak/CMPE492-Senior-Project.git"
robo-sim-py
```

The GitHub command works once these changes are pushed to the repository's default branch. For a local checkout:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .
python -m robo_sim_py
```

On Windows activate with `.venv\Scripts\activate`. PySide6 (Qt) is installed by pip; Tkinter is no longer required. On macOS start the editor with normal Python; it launches the MuJoCo worker using `mjpython` automatically. Linux desktop Qt requires the usual system graphics libraries; if Qt reports a missing `xcb-cursor` dependency on Ubuntu/Debian, install `libxcb-cursor0`.

## Command-line interface

Run `robo-sim-py` or `python -m robo_sim_py` to enter the interactive terminal interface.
When input is redirected, the default command prints help instead of waiting for input.
Open the existing desktop editor explicitly:

```bash
robo-sim-py --gui
# Equivalent:
python -m robo_sim_py --gui
```

Use `--help` or `run --help` for all options. Commands work both inside the
`robo-sim>` prompt and directly from your terminal (prefix them with `robo-sim-py`).

```bash
robo-sim-py list robots
robo-sim-py list presets
robo-sim-py run --preset 05_circle --robot simple_robot
robo-sim-py run --loop figure_eight --radius 3 --robot google_robot --no-auto-follow
robo-sim-py run --corridor 2 0 --corridor 1.5 90 --width 0.8
robo-sim-py run --scenario my-track.json --terrain random --height 0.003 --seed 42
robo-sim-py run --robot /path/to/robot.xml --scenario my-track.json
robo-sim-py run --scene /path/to/scene.xml
```

Preset selectors accept an exact display name (quoted if it contains spaces) or the
file stem shown by `list presets`. Built-in and saved presets are both available.
Custom robots default to manual controls; registered robots default to automatic
line following. `--auto-follow` and `--no-auto-follow` override that default for
registered robots. All dimensions, including terrain `--height`, use **metres**;
turns use degrees. Repeat `--corridor LENGTH TURN` for each section, starting with
a zero turn. Use `--spacing`, `--resolution`, `--line-width`, and `--radius` to
configure the same parameters as the editor. JSON/preset settings are loaded first,
then explicit options override them.

Inspect, edit, export, import into the library, and preview scenarios:

```bash
robo-sim-py scenario --loop circle --radius 3 --name "My circuit" --output my-track.json
robo-sim-py scenario --scenario my-track.json --name "Saved circuit" --save
robo-sim-py scenario --scenario my-track.json --width 1
robo-sim-py preview --scenario my-track.json
robo-sim-py validate my-track.json
robo-sim-py validate /path/to/scene.xml
robo-sim-py validate /path/to/experiment.zip
```

`scenario` prints JSON when neither `--save` nor `--output` is supplied.
`--description` changes the description; `--library DIRECTORY` selects an alternative
saved-scenario library. Exports refuse to overwrite existing files. `preview` opens
the same top-down schematic as the editor and needs a desktop display.

ZIP modes are detected automatically. Validation does not execute their Python code.
Execution requires explicit trust, just as in the editor:

```bash
robo-sim-py run --package robot.zip --preset 05_circle --trust-package
robo-sim-py run --package full-experiment.zip --trust-package
robo-sim-py run --package assignment.zip --menagerie /path/to/mujoco_menagerie --trust-package
```

Only robot ZIPs accept generated-track options. Full experiments and standalone
assignments provide their own environment. `--menagerie` supplies the optional local
dependency; standalone assignments also accept `--run-directory DIRECTORY` to retain
outputs at a chosen location. Imported Python has access to your files and network;
the simulation worker is a separate process, not a security sandbox.

In the interactive prompt, `run ...` starts the worker and returns control immediately.
Use `status`, `stop`, and `restart` to manage it. `restart --preset 05_circle` replaces
the run configuration; `restart` alone repeats the last request. A new `run ...`
validates its inputs before stopping the previous worker. `exit`, Ctrl+D, or Ctrl+C
at the prompt stops the worker and exits. Blank input does not repeat commands.
`--gui` opens the editor from the prompt too. Close preview/editor windows to return.

Direct terminal runs wait until the viewer closes; Ctrl+C stops them. Successful
commands return exit code 0, runtime/validation errors return 1, invalid command
syntax returns 2, and interrupted direct runs return 130. Viewer runs need a desktop
with OpenGL; this interface does not add headless simulation or batch execution.

After changing the installed console entry point, reinstall once:

```bash
python -m pip install -e .
```

## Choose an experiment mode

The top selector offers built-in experiments, **Assignment / full experiment ZIP**, **Robot + controller ZIP on generated track**, and direct scene XML loading. Existing track controls remain available for built-ins and robot packages. Full packages supply their own environment. Standard assignment ZIPs containing `python/main.py` and `scenes/` work without `experiment.json` or any particular ZIP/folder name; their script owns the simulation and generated files are retained in a run directory. Imported Python controllers require explicit trust approval and run in the separate simulation worker.

See [the experiment guide](docs/experiments.md) for the ZIP layout, `experiment.json`, controller API, Menagerie dependencies and extension registries. Runnable source examples are in [examples/](examples/); run `python examples/make_packages.py` to create both demo ZIPs, then browse to one in its matching mode.

## Create a scenario

1. Choose **Simple two-wheel robot** or **Google Robot (mobile adaptation)**, or browse for a custom MJCF XML.
2. Choose a scenario category: **Corridor tracks** contains Straight line, Left turn, Right turn, and Zigzag; **Loop tracks** contains Circle circuit and Figure-eight circuit. Saved scenarios appear in their matching category.
3. For corridors, edit the section count, lengths, and relative turns. For loops, edit the radius/scale. Both types have editable track and line widths. The top-down preview updates immediately. Positive turns go left, negative turns go right; the first corridor starts at the origin facing +X.
4. Use **Save to library…** to keep your edited scenario, or **Import JSON…** to load a scenario file. Switching presets prompts before discarding unsaved edits.
5. Leave **Automatically follow the line** checked to drive a bundled robot, or uncheck it for manual control. Custom XML has no automatic controller.
6. Click **Open MuJoCo simulation**. The editor remains responsive while MuJoCo runs in its own process. After selecting another scenario or editing parameters, click **Restart with selected scenario** to replace the running simulation. Selecting a preset updates the preview immediately; it does not change an already running MuJoCo world until you restart. Close the viewer or click **Stop simulation** to finish.

The corridors have white floors, black center lines, and solid light-gray walls on both sides. Walls are 0.3 m high and 2 cm thick, outside the specified usable corridor width. Corridor starts and finishes remain open; loop walls join continuously around the circuit. Consecutive strips share endpoints and have filled round joins; the walls follow the combined outline so they do not block the connections at bends or intersections. The editor preview shows the same wall layout. Sharp turns and self-intersections are allowed; intersecting tracks can create ambiguous routes for a future controller. The black line is visual and does not affect wheel contact, while the walls have physical collision enabled.

## Scenario library

Presets are versioned JSON files, independent of the robot model and controller. Both example robots can run the bundled presets. You can use the form to make a custom track and save it under a new name; saving never overwrites a bundled preset.

Built-in scenarios live in [scenarios/presets/](src/robo_sim_py/scenarios/presets/). To ship another corridor scenario, add a JSON file there using this format and reinstall (or use an editable install). No GUI registration or Python changes are required:

```json
{
  "version": 1,
  "name": "My left turn",
  "description": "Two connected corridors with a gentle turn.",
  "width": 0.8,
  "line_width": 0.025,
  "corridors": [
    {"length": 2.0, "turn": 0.0},
    {"length": 1.5, "turn": 45.0}
  ]
}
```

User scenarios are loaded automatically on the next launch from:

- Linux: `$XDG_DATA_HOME/line-tracker-sim/scenarios`, defaulting to `~/.local/share/line-tracker-sim/scenarios`.
- macOS: `~/Library/Application Support/line-tracker-sim/scenarios`.
- Windows: `%LOCALAPPDATA%/line-tracker-sim/scenarios`.

**Import JSON…** loads a file for the current session; use **Save to library…** to retain it between launches. Invalid scenario files are reported without preventing other presets from loading. Version 1 describes corridor tracks and remains supported unchanged. Version 2 supports the loop type described below. Other environment types, such as obstacle fields, would also need a new geometry builder.

[scenarios/library.py](src/robo_sim_py/scenarios/library.py) handles validation, discovery, and persistence. [ui/editor.py](src/robo_sim_py/ui/editor.py) manages the Qt editor, [ui/preview.py](src/robo_sim_py/ui/preview.py) draws the schematic, and [simulation/__main__.py](src/robo_sim_py/simulation/__main__.py) launches the separate MuJoCo process. The physics and controllers remain independent of the UI toolkit.

## Loop tracks

**Loop tracks** is a separate selector category, not another corridor preset. The built-in options are:

- **Circle circuit:** 2 m radius, closed walls and a marked start line.
- **Figure-eight circuit:** an infinity-shaped track at 3 m scale, with an open, flat central crossing. It has no bridge; both lobes share the crossing.

Both start at the origin facing +X. With automatic driving enabled, the controller follows the ordered route and repeats laps until you stop the simulation. It does not finish or brake at the end of the first lap. The route order prevents it from taking the wrong branch at the figure-eight crossing. These examples use the existing automatic geometric controller, not the manual control required by the racing assignment.

The curves use short connected segments for physics. The loop size must be at least twice the track width; smaller tight turns are not supported by the editor. This geometric validation does not guarantee that every robot can handle every size.

Loop JSON uses version 2:

```json
{
  "version": 2,
  "type": "loop",
  "name": "My circular circuit",
  "description": "Continuous laps around a circle.",
  "shape": "circle",
  "radius": 2.0,
  "width": 0.8,
  "line_width": 0.025
}
```

Use `"shape": "figure_eight"` with `"radius": 3.0` for the infinity-shaped example (the radius field acts as its overall scale). Import and Save to library support both types and retain their category. In Python, use `LoopScenario("circle", radius=2.0)` or `LoopScenario("figure_eight", radius=3.0)`. The controller exposes a `laps` count, which resets with the simulation.

## Robot files

Select a complete MJCF model with a `<mujoco>` root. Keep any included XML, meshes, and textures at the paths referenced by that model; the loader reads from its original directory using MuJoCo's [model editing API](https://mujoco.readthedocs.io/en/stable/python.html#model-editing). There is no need to select each asset separately. Missing assets or invalid models are reported in the form. Source model files are never modified.

Use a robot-only model without its own floor or scenery. The generated floor surface is at z=0. Position the robot at `(0, 0)` with the correct body height for its wheels and orient its forward direction along +X. Model poses, actuators and sensors are retained. A mobile robot needs a free joint or suitable planar joints; a fixed robot stays fixed.

The small example robot includes two driven wheels, front and rear low-friction supports, motor actuators, and a sensor mounting site. Both examples use automatic controllers with **ideal geometric sensing**: the known, ordered track center line and MuJoCo's robot pose. They steer toward a look-ahead point on the route (12 cm for the small robot, 16 cm for Google Robot) and control wheel speeds through bounded motor torques. Motion comes from wheel contact and physics, without teleporting the robot or setting its pose.

This is a baseline path-following controller, **not a camera or reflectance sensor simulation**. It has no perception noise and knows the route through intersections. It slows for heading errors, stops within roughly 5 cm of the endpoint, and brakes if it strays more than 30 cm from the current section. Resetting the simulation resets controller progress. Each example configures its own wheel dimensions, speed, steering limits, and motor feedback gain; custom robots still require their own control integration.

Straight routes, left/right 90° turns, a 135° turn, and a three-section route are covered by physics tests. Extremely short sections, narrow corridors, and other sharp/self-overlapping layouts are not guaranteed to be traversable by this robot.

After updating the source, reinstall before launching (or use `python -m pip install -e .` during development):

```bash
python -m pip install .
python -m robo_sim_py
```

## Example layout and adding robots

Each example keeps its model and controller together:

- [assets/simple_robot/](src/robo_sim_py/assets/simple_robot/): [robot.xml](src/robo_sim_py/assets/simple_robot/robot.xml) and [controller.py](src/robo_sim_py/assets/simple_robot/controller.py).
- [assets/google_robot/](src/robo_sim_py/assets/google_robot/): [robot.xml](src/robo_sim_py/assets/google_robot/robot.xml), [controller.py](src/robo_sim_py/assets/google_robot/controller.py), meshes/textures, upstream license, and [adaptation notes](src/robo_sim_py/assets/google_robot/MODEL_NOTES.md).

The Google example adapts the Menagerie fixed-base robot with a free base, driven wheels, approximate base inertia and support contacts. Its controller holds the arm while driving. The original Menagerie checkout is not needed at runtime. The added base dynamics are approximations, not a hardware-calibrated model. Start with the default 0.8 m corridor width or wider.

[assets/tracking.py](src/robo_sim_py/assets/tracking.py) contains the shared steering and wheel-feedback algorithm. Robot-specific controllers configure or extend it. [assets/__init__.py](src/robo_sim_py/assets/__init__.py) maps each bundled model to its controller and supplies the GUI choices. The obsolete top-level controller wrapper has been removed; import a robot-specific controller directly if needed.

To add another supported example, create a package under the assets directory with its model, assets, controller and `__init__.py`, then register a `RobotExample` in the registry. Controllers accept `(model, scenario)` and provide `update(data)`. Registering it makes it appear in the GUI without adding robot-specific GUI or simulation branches. Custom XML can still be loaded for manual simulation; Python files beside arbitrary XML are never automatically executed. Additional asset file formats must also be included in the package-data configuration.

## Python API and verification

```python
from robo_sim_py import Corridor, Scenario
from robo_sim_py.simulation import build_model, example_robot, run

scenario = Scenario((Corridor(2), Corridor(1.5, 90), Corridor(2, -45)))
robot_path = example_robot("google_robot")  # or "simple_robot"
model = build_model(robot_path, scenario)
run(model, scenario, auto_follow=True, robot_path=robot_path)
```

Run headless tests after installation with `python -m unittest discover -s tests`. These check geometry, validation, model loading, actual driving through turns, endpoint braking, and controller reset; the Qt editor tests use offscreen rendering, while interactive MuJoCo requires a desktop display.

The broader research proposal remains in [ReadME.txt](ReadME.txt).

## Adjustable height-field terrain

In **Ground surface**, choose **Flat**, **Smooth waves**, or **Random bumps**. This works with corridor and loop scenarios. Flat remains the default for existing presets.

- **Height variation:** peak-to-valley elevation, 0–30 cm. Start at the default **0.3 cm**; robot clearance and available motor torque limit what it can traverse.
- **Bump spacing:** wavelength in metres (random terrain mixes wavelengths from this value to twice this value). Larger values make gentler slopes.
- **Grid resolution:** number of height samples along the longest terrain dimension, 33–513. Higher values resolve smaller bumps at greater physics cost. Tracks with fewer than six samples per requested wavelength are rejected; increase resolution or spacing.
- **Random seed:** reproduces the same bumps for the same track and parameters. It affects Random bumps only.

The surface is a collidable MuJoCo `hfield`, with the road and line painted onto it. Walls follow its elevation. A level patch around the origin preserves the starting pose of the bundled robots. Custom robots should fit this starting patch (0.45 m radius) and supply their usual wheel-on-z=0 starting height. The preview remains a top-down schematic; terrain elevation is visible in MuJoCo. At very large track sizes the capped marking texture may render the line wider than its requested width.

**Save to library** and **Import JSON** preserve terrain settings. Either scenario JSON format accepts an optional field:

```json
"terrain": {"mode": "random", "height": 0.003, "spacing": 0.8, "resolution": 129, "seed": 42}
```

JSON/Python height uses **metres**; the GUI displays **centimetres**. In Python, pass `terrain=Terrain("random", height=0.003, spacing=0.8, resolution=129, seed=42)` to `Scenario` or `LoopScenario` (import `Terrain` from `robo_sim_py`). Generation and surface painting live in [simulation/terrain.py](src/robo_sim_py/simulation/terrain.py).

The existing controllers were tuned for flat ground. The Google example can stall on slopes or at turns, even with small bumps; successful completion is not guaranteed. Terrain settings deliberately allow experiments beyond either robot's capabilities.

If bumps look flat, remember that the default 0.3 cm is only 3 mm. For a visual inspection, disable automatic driving and try 5–10 cm height with 0.8 m spacing, then click **Restart with selected scenario** (or open a new simulation). These larger bumps may be undrivable. The start patch remains level; inspect the surface farther along the track. Tall walls can obscure the road from low camera angles. Terrain uses oblique lighting to make slopes easier to distinguish.

## Import a complete MuJoCo scene

Choose **Import MuJoCo scene XML** in the source selector at the top of the editor, browse to the scene's XML, and click **Open MuJoCo scene**. Use **Restart with imported scene** to replace a running simulation. Switch back to **Generated track** to return to the existing robot, circuit, and terrain editor; its settings are retained.

This mode loads the scene **as supplied** using MuJoCo's XML loader. Relative includes, meshes, and textures must remain in their expected folders. The scene's environment, included robots, physics options, and lighting are preserved; no generated floor, walls, or extra robot are added. XML or missing-asset errors appear in the editor.

An environment-only XML opens without a robot. To drive a robot in it, the complete scene XML must already include that robot and its actuators. Combining a separately selected robot with an imported environment is not part of this mode. Automatic line following is unavailable because an arbitrary scene does not define our controller's ordered route. Where actuators exist, their controls are available in the MuJoCo viewer; there is no new keyboard driving controller. Importing a scene does not execute Python controllers beside the XML.

Imported scenes are selected directly from disk; **Import JSON** and **Save to library** remain specific to generated scenarios. From Python, use `load_scene(path)` and `run(model)` from `robo_sim_py.simulation`.


## Generate a scene without opening the application

The CLI can build the existing ground and wall structures and export an
**environment-only** MuJoCo scene without starting Qt, a viewer, or a simulation:

```bash
python -m robo_sim_py generate --corridor 2 0 --corridor 1.5 90 --terrain flat --output scene.xml
python -m robo_sim_py generate --loop circle --radius 2 --terrain waves --height 0.02 --output waves.xml
python -m robo_sim_py generate --preset 04_zigzag --terrain random --seed 7 --output bumps.xml
python -m robo_sim_py validate scene.xml
python -m robo_sim_py run --scene scene.xml
```

`generate` accepts the same preset, scenario JSON, corridor, loop, width, and terrain
options as `run`. Its output defaults to `scene.xml`; existing files are never
overwritten. The output's parent directory must already exist. Random terrain
uses the existing seed; wall layouts still come from explicit corridors or loop
parameters, rather than a new random maze generator.

Flat exports need only the XML. Uneven terrain also produces a sibling directory,
for example `waves_assets/`, containing the road-marking PNG. Keep that directory
beside the XML when moving or sharing it. Height-field elevations are stored in
the XML itself. Existing asset directories are not overwritten either.

The exported scene has no robot or automatic controller. `run --scene` opens it
for inspection using the existing scene-loading workflow. To run a bundled robot
with automatic following, use the same generation options with `run` instead:

```bash
python -m robo_sim_py run --preset 04_zigzag --terrain random --seed 7 --robot simple_robot
```

Both CLI generation and the existing GUI/robot workflow use the ordered pipeline
in `simulation/generation.py`: ground and road markings, terrain-aware walls,
then lighting. A `GenerationContext` carries the MuJoCo spec, scenario, defaults,
and generated terrain (including elevation queries). `GenerationPipeline` accepts
an ordered tuple of stage callables, so future static and dynamic obstacle stages
can be inserted after walls without changing the ground or wall builders. No
obstacle stages are implemented yet. Existing presets and scenario JSON remain
compatible; save the scenario JSON alongside an export when you want to retain
editable generation parameters.
