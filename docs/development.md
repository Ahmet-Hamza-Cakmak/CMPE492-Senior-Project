# Architecture and Python API

[Documentation index](README.md) · [Project README](../README.md)

Commands and source paths assume the repository root unless stated otherwise.

## Project organization

Application code is grouped by responsibility under [src/robo_sim_py/](../src/robo_sim_py/):

| Area | What belongs here |
| --- | --- |
| [ui/](../src/robo_sim_py/ui/) | [editor.py](../src/robo_sim_py/ui/editor.py) contains the PySide6 window and process controls; [preview.py](../src/robo_sim_py/ui/preview.py) draws the track preview. |
| [scenarios/](../src/robo_sim_py/scenarios/) | [__init__.py](../src/robo_sim_py/scenarios/__init__.py) defines corridor and loop geometry; [library.py](../src/robo_sim_py/scenarios/library.py) loads/saves scenarios; [presets/](../src/robo_sim_py/scenarios/presets/) holds built-in track and maze configurations. |
| [simulation/](../src/robo_sim_py/simulation/) | [__init__.py](../src/robo_sim_py/simulation/__init__.py) builds and runs MuJoCo models; [walls.py](../src/robo_sim_py/simulation/walls.py) calculates wall geometry; [__main__.py](../src/robo_sim_py/simulation/__main__.py) is the separate viewer process entry point. |
| [assets/](../src/robo_sim_py/assets/) | [__init__.py](../src/robo_sim_py/assets/__init__.py) registers robot examples; [tracking.py](../src/robo_sim_py/assets/tracking.py) provides shared driving logic. Each robot folder keeps its controller, XML, and supporting assets together. |
| [experiments/](../src/robo_sim_py/experiments/) | Validates ZIP packages and manifests; defines the controller context, lifecycle and robot placement. |
| [tests/](../tests/) | Geometry, driving, UI, persistence, and worker-process regression tests. |

The package's [__main__.py](../src/robo_sim_py/__main__.py) is intentionally small: it starts the terminal interface; `--gui` opens the editor. Small robot controller files are also intentional—they configure shared tracking logic rather than duplicate it. Package marker files establish Python import boundaries.

To change the UI, start in the UI folder. To add a preset, add JSON in the preset folder. To add a robot, create its asset folder and register it in the asset registry. To change physics or walls, use the simulation folder.

The public imports `from robo_sim_py import Corridor, Scenario, LoopScenario` and `from robo_sim_py.simulation import build_model, example_robot, run` remain unchanged. Internal imports moved to their corresponding areas; the old flat modules are removed. User-saved scenarios remain in the same application-data directory and require no migration.

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

- [assets/simple_robot/](../src/robo_sim_py/assets/simple_robot/): [robot.xml](../src/robo_sim_py/assets/simple_robot/robot.xml) and [controller.py](../src/robo_sim_py/assets/simple_robot/controller.py).
- [assets/google_robot/](../src/robo_sim_py/assets/google_robot/): [robot.xml](../src/robo_sim_py/assets/google_robot/robot.xml), [controller.py](../src/robo_sim_py/assets/google_robot/controller.py), meshes/textures, upstream license, and [adaptation notes](../src/robo_sim_py/assets/google_robot/MODEL_NOTES.md).

The Google example adapts the Menagerie fixed-base robot with a free base, driven wheels, approximate base inertia and support contacts. Its controller holds the arm while driving. The original Menagerie checkout is not needed at runtime. The added base dynamics are approximations, not a hardware-calibrated model. Start with the default 0.8 m corridor width or wider.

[assets/tracking.py](../src/robo_sim_py/assets/tracking.py) contains the shared steering and wheel-feedback algorithm. Robot-specific controllers configure or extend it. [assets/__init__.py](../src/robo_sim_py/assets/__init__.py) maps each bundled model to its controller and supplies the GUI choices. The obsolete top-level controller wrapper has been removed; import a robot-specific controller directly if needed.

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

The broader research proposal remains in [ReadME.txt](../ReadME.txt).
