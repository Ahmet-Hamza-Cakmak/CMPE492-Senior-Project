# Python API

[Documentation index](README.md) · [Project README](../README.md)

NavProbe is library-first: existing configuration, generation, persistence,
validation, and execution operations are available as Python calls. CLI and GUI
adapt these shared services. You do not need an argument parser or a GUI to use them.

The API is alpha. These services require NavProbe `0.1.0a2` or later; the older
`0.1.0a1` release does not contain this complete service API.

## Start with the shared services

```python
from navprobe import (
    ScenarioOptions, RunOptions, create_scenario, export_scenario,
    generate_environment, open_simulation, prepare_run,
)

preset = create_scenario(ScenarioOptions(
    maze=True, maze_rows=4, maze_columns=4, maze_algorithm="prim",
    layout_seed=7, robot="simple_robot",
))
export_scenario(preset, "case.json")  # explicit, optional persistence
result = generate_environment(preset, "scene.xml")

request = prepare_run(RunOptions(scenario=preset, robot="simple_robot"))
with open_simulation(request) as session:  # no desktop/viewer required
    session.step(1000)
    print(session.data.time, session.data.qpos.copy())
```

Functions also accept keyword options: `create_scenario(maze=True, maze_rows=4)`
and `open_simulation(scenario=preset, robot="simple_robot")` are equivalent forms.
Use the prepared scenario/request again when comparing inputs; running does not
save an automatic scenario archive.

| Operation | Python service | Result |
| --- | --- | --- |
| List robots | `list_robots()` | Tuple of registered `RobotExample` values |
| List presets | `list_presets(library=None)` | `PresetCatalog(entries, errors)`; errors are data, not terminal warnings |
| Configure/load/edit/sample | `create_scenario(options=None, **changes)` | Prepared `ScenarioPreset` |
| Configure with metadata | `configure_scenario(options=None, **changes)` | `ScenarioResult(preset, footprint, warnings)`; `.scenario` accesses the scenario |
| Generate XML | `generate_environment(options=None, destination="scene.xml", **changes)` | `GeneratedEnvironment(path, result)` |
| Export JSON | `export_scenario(preset, destination)` | New JSON `Path`; existing files are refused |
| Save to preset library | `save_preset(preset, directory)` | New library JSON `Path` |
| Load JSON | `load_preset(path)` | `ScenarioPreset` |
| Validate JSON/XML/ZIP | `validate_input(path, menagerie=None)` | `ValidationResult(kind, name, path, mode, digest)` |
| Prepare a run | `prepare_run(options=None, **changes)` | Frozen `RunRequest`; no controller execution/viewer |
| Step physics in Python | `open_simulation(options=None, **changes)` | `SimulationSession`; use a context manager |
| Run normally | `run_experiment(options=None, **changes)` | Blocking viewer or standalone ZIP entry point; no viewer until called |
| Start a worker | `start_simulation(options=None, **changes)` | `subprocess.Popen`; inspect `poll()` / `wait()` for status |
| Stop / restart a worker | `stop_simulation(process)`, `restart_simulation(process, options=None, **changes)` | Reaped process / replacement `Popen` |
| Preview / GUI | `preview_scenario(preset)`, `open_gui()` | Explicit blocking desktop operations; return exit status |

`ScenarioOptions`, `RunOptions`, and all services above are available from
`navprobe`. They also live in `navprobe.services`, `navprobe.execution`, and
`navprobe.interfaces`. Lower-level generation, navigation, scenario, controller,
robot, and simulation modules remain available under their existing imports.

## Settings and CLI correspondence

Option names match CLI flags with hyphens replaced by underscores. Omitted
(`None`) scenario overrides retain the source's value. Constructors reject
unknown field names. The `from_mapping()` helpers are intended for interface
adapters and deliberately ignore unrelated interface fields.

| Group | `ScenarioOptions` fields |
| --- | --- |
| One source | `scenario` (JSON path, scenario object, or preset), `preset` (name/stem), `scenic` (trusted Scenic path), `maze`, `dungeon`, `loop`, `corridor` (ordered `(length, turn)` pairs) |
| Source metadata | `scenic_seed`, `library`, `name`, `description` |
| Shared layout | `width`, `line_width`, `radius` (loop size) |
| Maze | `maze_algorithm`, `maze_rows`, `maze_columns`, `cell_size`, `newest_probability`, `loop_fraction` |
| Dungeon | `map_width`, `map_height`, `rooms`, `room_min`, `room_max`, `room_shape` |
| Layout randomness | `layout_seed` |
| Terrain | `terrain` (flat/waves/random), `height`, `spacing`, `resolution`, `seed` |
| Population | `static_objects` (count), `object_seed`, `object_min_size`, `object_max_size`, `object_height`, `object_clearance`, `object_placement` |
| Robot sizing | `robot`, `robot_radius`, `footprint_margin`, `robot_body` |

`RunOptions` includes those fields and adds `scene`, `package`, `auto_follow`,
`navigation`, `grid_resolution`, `navigation_clearance`, `simulation_speed`,
`menagerie`, `run_directory`, `trust_package`, and optional `approved_sha256`.
Only one of `robot`, `scene`, or `package` may select an execution source. Without
one, the simple robot is selected. `scene` and full packages reject generated
layout overrides. Robot-only packages accept generated scenarios. `auto_follow`
defaults on only for registered robots; explicit A* requires the simple robot on
flat terrain. Grid/clearance overrides require A*. See [scenario parameters](scenarios.md)
for units, limits, and defaults; the same validation applies to Python, CLI, and GUI.

`configure_scenario` and `generate_environment` accept either `ScenarioOptions`
or an existing scenario/preset. `prepare_run`, execution, and worker-control
services accept `RunOptions` or keyword settings; execution also accepts a
prepared `RunRequest`. The latter freezes sampled scenario values for subsequent execution; robot XML
and external assets are still read from their paths and are not archived.
A prepared request cannot be combined with overrides; prepare a new request instead.

## Execution, cleanup, and errors

```python
from navprobe import RunOptions, prepare_run, open_simulation, run_experiment

request = prepare_run(RunOptions(scenario="case.json", robot="simple_robot"))
with open_simulation(request) as session:
    session.step(500)
    position = session.data.qpos.copy()
    session.reset()
# session is closed; later step/reset calls raise RuntimeError

# Explicitly open the normal viewer instead:
# run_experiment(request)
```

A session exposes `model`, `data`, `controller`, `context`, `request`, and `closed`.
`open_simulation(..., controller=my_controller, context=None, auto_follow=False)`
also accepts a native Python controller without a ZIP. It must implement
`reset(model, data, context)`, `step(model, data, context)`, and `close()`.
A default `ControllerContext` supplies the scenario/route and model directory;
a custom context may be supplied. Combining it with a package or automatic
bundled controller is rejected. The session owns cleanup after successful setup.

`step(steps=1)` advances a positive integer number of physics steps, with controller
updates, and returns `data`; `reset()` restores the model's initial state and
resets its controller. `close()` is idempotent. Context-manager exit closes the
controller before releasing imported temporary files, even when the body raises.
Headless stepping has no viewer pacing; `simulation_speed` affects viewer
playback only. Runtime monitoring, dynamic agents, and automated campaigns remain
planned; a session is an individual simulation, not a campaign/monitor service.

Core services return Python values and do not print progress or parse terminal
output. Invalid settings raise `ValueError` (or `TypeError` for incorrect API
arguments), file errors raise `OSError`, and runtime/controller errors propagate.
Closed sessions raise `RuntimeError`. MuJoCo may raise its own model/physics errors.
These calls do not call `sys.exit`; a controller's requested `SystemExit` is
translated to `RuntimeError`. Standalone entry points exiting with status zero
are successful; nonzero exit status becomes `RuntimeError`. User Python and
third-party tools may still produce output or have arbitrary process effects.

Imported Python requires `trust_package=True`. `prepare_run` validates the ZIP
and records its SHA-256 without importing controller code; execution rechecks
that hash. `approved_sha256` additionally pins a previously inspected ZIP, as used
by the GUI approval dialog. A robot-only ZIP's model is used for footprint
inference; a full ZIP supplies its own environment. Standalone scripts run their
own loop, so `open_simulation` rejects them; use `run_experiment` or
`start_simulation` instead. An explicit `run_directory` is available only for
standalone scripts. Use a fresh output directory for each standalone execution;
existing directories are never overwritten. Their working files are separate from automatic scenario
archiving, which remains outside scope.

In-process imported controllers/scripts are trusted Python, not sandboxed or
guaranteed thread-safe. Their imports and global state may affect the host.
Use worker processes for independent executions. `restart_simulation` prepares
the replacement before stopping the old worker. Always close sessions and stop
workers when finished. No persistent files are created by a normal managed run.

Importing `navprobe`, its root exports, or the service modules starts no CLI,
Qt application, viewer, or simulation. Optional Qt and Scenic are loaded only
when their operations are explicitly requested. Headless sessions need MuJoCo
but do not import `mujoco.viewer`.

## Robot-aware generation

```python
from navprobe import MazeScenario, example_robot, prepare_scenario, export_scene

scenario, footprint = prepare_scenario(
    MazeScenario(rows=4, columns=6),
    robot_path=example_robot("simple_robot"),
    margin=0.05,
)
print(footprint.raw_radius, footprint.radius)  # metres
export_scene(scenario, "robot-aware-maze.xml")
```

`estimate_robot_footprint(robot_path, *, margin=0.05, body=None)` returns a frozen
`RobotFootprint` with `body`, `raw_radius`, `margin`, `radius`, and `geometry_count`.
It loads MJCF/includes/assets in place and uses MuJoCo collision-geometry bounding
boxes transformed at `qpos0`. It does not step physics or execute a controller.
It excludes world and purely visual geometry. The enclosing circle is centred on
the selected body origin; multiple candidate trees require `body="name"`.
This deliberately conservative estimate includes initial-pose articulated parts,
not their future motion, and does not guarantee dynamic or turning feasibility.

`prepare_scenario(scenario, *, robot_path=None, robot_radius=None, margin=0.05,
body=None)` returns `(prepared_scenario, inferred_footprint_or_none)`. It resolves
the radius before sampling and checks planar mission connectivity before and
after population. A positive `robot_radius` overrides inference and is the final
radius (no additional margin). Without a model or override, the stored/default
radius is retained. Existing concrete placements are revalidated rather than
silently resampled. Invalid/ambiguous geometry or disconnected mission anchors
raise `ValueError`; enlarge the scene or supply an appropriate override.

Use the returned scenario for export, model building, planning, and controller
context so all operations use the same geometry and radius. Lower-level
`export_scene`/`build_model` consume the supplied scenario; they do not resolve
footprints independently. CLI and GUI use this shared preparation service.

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
