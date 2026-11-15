# Python API

[Documentation index](README.md) · [Project README](../README.md)

Use `navprobe` for new Python integrations. Common operations are available at the
package root; related functions also have public modules:

| Import | Contents |
| --- | --- |
| `navprobe` | Scenario types, static-object settings, presets, population, XML export, model loading/building, simulation, and A* planning |
| `navprobe.scenarios` | Scenario types, `ScenarioPreset`, preset discovery/save/load, Scenic sampling, concrete population, and planar geometry |
| `navprobe.generation` | `GenerationPipeline`, `GenerationContext`, callable stages, `generate_spec`, and `export_scene` |
| `navprobe.simulation` | `example_robot`, `build_model`, `load_scene`, and `run` |
| `navprobe.navigation` | `PlannedRoute`, `astar`, `plan_scenario`, and route drawing |
| `navprobe.controllers` | `Controller`, `ControllerContext`, bundled adapter, and managed controller loading |
| `navprobe.robots` | Bundled examples, robot registration, and controller selection |
| `navprobe.experiments` | `Experiment`, `open_package`, and `run_full_zip` for full ZIP entry-point scripts |

The full implementation, CLI, GUI, and public API live under `src/navprobe/`.
Convenience imports reference the same classes and functions as the detailed
modules; there is a single implementation namespace.
The API is alpha and can evolve between releases. This guide describes the source
checkout; the new exports will be included in the next PyPI release.

Importing these modules does not open the CLI, GUI, or simulation viewer, or import
Qt or Scenic. The root namespace resolves exports on demand. Install the base
package for generation and MuJoCo; add `[scenic]` for new constrained samples.
`[gui]` is needed only for the editor/preview. A MuJoCo viewer requires a desktop
with graphics support but does not require the GUI extra.

## Generate an environment

```python
from navprobe import MazeScenario, export_scene

scenario = MazeScenario(rows=4, columns=6, algorithm="prim", layout_seed=7)
scene_path = export_scene(scenario, "maze.xml")
```

`export_scene(scenario, destination, *, pipeline=None)` returns a `Path`. It
exports an environment without a robot or controller and does not start a viewer.
The parent directory must exist; existing output files/assets are not overwritten.
Uneven-terrain exports can create a sibling assets directory. Invalid settings or
unsupported geometry raise `ValueError`; file operations can raise `OSError`.

For a corridor or loop, use `Scenario((Corridor(length, turn), ...))` or
`LoopScenario(...)`. `Terrain(...)` configures supported surfaces. Distances are
metres and corridor turns are degrees. See [scenario settings](scenarios.md) for
ranges and restrictions shared with CLI and GUI.

## Populate and save a reusable scenario

```python
from navprobe import (
    MazeScenario, StaticObjectSettings, ScenarioPreset,
    populate_scenario, save_preset, load_preset,
)

scenario = MazeScenario(
    rows=4, columns=4,
    objects=StaticObjectSettings(count=3, seed=9),
)
scenario = populate_scenario(scenario)  # Requires Scenic for a new sample.
preset = ScenarioPreset("Maze with boxes", "Seeded static population", scenario)
json_path = save_preset(preset, "my-scenarios")
restored = load_preset(json_path).scenario
```

`populate_scenario` returns a scenario with concrete placements; it does not mutate
the original frozen configuration. It reuses existing concrete placements and
needs no Scenic when population is disabled. Sampling failures raise `ValueError`.
`save_preset(preset, directory)` creates the directory if needed and returns a
new JSON path. `load_preset(path)` returns a validated `ScenarioPreset`;
`parse_preset(payload)` accepts a decoded JSON dictionary. `ScenarioPreset.to_dict()`
produces serializable data and freezes requested population when necessary.

Changing a scenario's geometry or population settings through `dataclasses.replace`
requires clearing incompatible saved placements with `static_objects=None` before
resampling. Manual scenario saving preserves configuration when requested. Automatic test-case
archiving, provenance management, and experiment replay are outside project scope.

## Map and controller inputs

The current geometry API exposes Python objects before XML export:

```python
from navprobe.scenarios import placement_geometry, static_objects

geometry = placement_geometry(scenario)
floor = geometry.floor
mission_anchors = geometry.anchors
reference_route = geometry.route
obstacle_polygons = tuple(box.footprint() for box in static_objects(scenario))
```

- `geometry.floor` is a Shapely polygon or multipolygon describing the planar
  floor. It has not had obstacle footprints subtracted or robot clearance applied.
- `geometry.route` is the reference route; population can obstruct it.
- `geometry.anchors` identifies mission points. Open layouts use endpoints;
  loops use four quarter-lap points.
- `geometry.passages` contains available passage geometry.
- `StaticBox.footprint()` returns a Shapely polygon; box `yaw` is in radians.

XY values are world coordinates in metres, +Z is up, and the bundled robot starts
facing +X. This is ideal knowledge of generated static geometry. It supplies no
sensor observations or SLAM estimate, and planar geometry does not certify travel
on uneven terrain. This interface is the current geometry representation; a
separate general map/mission contract remains planned.

Managed controllers receive `ControllerContext` through `reset(model, data,
context)` and `step(model, data, context)`. `context.scenario` contains the
generated scenario in robot-package mode and is `None` for a complete imported
experiment. `context.route` is a reference route, rather than an A* result.
Simulation calls `step` before physics advances; `data.time` is simulation time in
seconds. See the [controller guide](experiments.md#controller-api) for the complete
lifecycle, context fields, and a minimal controller.

## Plan and run a robot

```python
from navprobe import (
    MazeScenario, plan_scenario, example_robot, build_model, run,
)

scenario = MazeScenario(rows=4, columns=4)
route = plan_scenario(scenario, resolution=0.25)
print(route.points, route.length)

robot_path = example_robot("simple_robot")
model = build_model(robot_path, scenario)
run(model, scenario, auto_follow=True, robot_path=robot_path,
    navigation="astar", simulation_speed=5)
```

`plan_scenario(scenario, *, resolution=0.25, clearance=None)` supports generated flat
layouts and returns `PlannedRoute`: world-XY `points`, length in metres, expanded
node count, and actual grid resolution. It accounts for static obstacle footprints
and configured clearance. It raises `ValueError` when a supported route cannot be
found or inputs are invalid. Lower-level `astar(floor, obstacles, start, goal, ...)`
accepts Shapely geometry and world-XY endpoints directly.

`build_model(robot_path, scenario, *, pipeline=None)` returns a compiled
`mujoco.MjModel`. `load_scene(scene_path)` loads existing XML unchanged. These
operations do not launch a viewer. MuJoCo can raise exceptions for invalid models
or missing assets.

`run(model, scenario=None, *, ...)` explicitly opens the MuJoCo viewer and blocks
until it closes. `auto_follow`, `robot_path`, `navigation`, `grid_resolution`,
`navigation_clearance`, and `simulation_speed` configure the bundled controller.
Explicit A* driving requires the simple robot on flat ground; automatic selection
uses the same rules as the CLI. The controller computes its own route from the
scenario, so the separately computed `route` above is for inspection. A custom
managed controller can instead be supplied with `controller=` and `context=`.
Playback speed affects pacing; physics timestep and simulation-time semantics
stay unchanged. Headless campaign execution and dynamic replanning remain planned. Automatic
archiving of tested environments and historical replay are outside project scope.

For a robot with actuators loaded from XML, `run(model)` does not automatically
attach a Python controller. XML loading is distinct from managed controller
execution.

## Migrating earlier alpha integrations

Replace `robo_sim_py` with `navprobe` in Python imports and module commands.
For example, `from robo_sim_py.simulation import run` becomes
`from navprobe.simulation import run`. The old Python namespace is removed by
the full rename. Update controller code inside imported experiment archives too.
`robo-sim-py` remains a console-command alias; both console commands now call
`navprobe.cli:main`. Saved scenario JSON and XML layouts keep their formats.

After updating a source checkout, reinstall it with
`python -m pip install -e '.[all,dev]'` so console scripts and editable-package
metadata point at the renamed modules. Existing PyPI releases do not change.
