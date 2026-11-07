# CLI and simulation workflows

[Documentation index](README.md) · [Project README](../README.md)

Commands and source paths assume the repository root unless stated otherwise.

## Command-line interface

Run `navprobe` or `python -m robo_sim_py` to enter the interactive terminal interface.
When input is redirected, the default command prints help instead of waiting for input.
Open the existing desktop editor explicitly:

```bash
navprobe --gui
# Equivalent:
python -m robo_sim_py --gui
```

Use `--help` or `run --help` for all options. Commands work both inside the
`navprobe>` prompt and directly from your terminal (prefix them with `navprobe`).

```bash
navprobe list robots
navprobe list presets
navprobe run --preset 05_circle --robot simple_robot
navprobe run --loop figure_eight --radius 3 --robot google_robot --no-auto-follow
navprobe run --corridor 2 0 --corridor 1.5 90 --width 0.8
navprobe run --scenario my-track.json --terrain random --height 0.003 --seed 42
navprobe run --robot /path/to/robot.xml --scenario my-track.json
navprobe run --scene /path/to/scene.xml
```

Preset selectors accept an exact display name (quoted if it contains spaces) or the
file stem shown by `list presets`. Built-in and saved presets are both available.
Custom robots default to manual controls; registered robots default to automatic
driving (A* for simple-robot dungeons, line following otherwise). `--auto-follow` and `--no-auto-follow` override that default for
registered robots. All dimensions, including terrain `--height`, use **metres**;
turns use degrees. Repeat `--corridor LENGTH TURN` for each section, starting with
a zero turn. Use `--spacing`, `--resolution`, `--line-width`, and `--radius` to
configure the same parameters as the editor. JSON/preset settings are loaded first,
then explicit options override them.

Inspect, edit, export, import into the library, and preview scenarios:

```bash
navprobe scenario --loop circle --radius 3 --name "My circuit" --output my-track.json
navprobe scenario --scenario my-track.json --name "Saved circuit" --save
navprobe scenario --scenario my-track.json --width 1
navprobe preview --scenario my-track.json
navprobe validate my-track.json
navprobe validate /path/to/scene.xml
navprobe validate /path/to/experiment.zip
```

`scenario` prints JSON when neither `--save` nor `--output` is supplied.
`--description` changes the description; `--library DIRECTORY` selects an alternative
saved-scenario library. Exports refuse to overwrite existing files. `preview` opens
the same top-down schematic as the editor and needs a desktop display.

ZIP modes are detected automatically. Validation does not execute their Python code.
Execution requires explicit trust, just as in the editor:

```bash
navprobe run --package robot.zip --preset 05_circle --trust-package
navprobe run --package full-experiment.zip --trust-package
navprobe run --package assignment.zip --menagerie /path/to/mujoco_menagerie --trust-package
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

See [the experiment guide](experiments.md) for the ZIP layout, `experiment.json`, controller API, Menagerie dependencies and extension registries. Runnable source examples are in [examples/](../examples/); run `python examples/make_packages.py` to create both demo ZIPs, then browse to one in its matching mode.

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
optional static objects for all layouts, then lighting. A `GenerationContext` carries the MuJoCo spec, scenario, defaults,
and generated terrain (including elevation queries). `GenerationPipeline` accepts
an ordered tuple of stage callables. Static boxes use a shared stage after
walls; future object types and dynamic agents can extend the same interface. Existing presets and scenario JSON remain
compatible; save the scenario JSON alongside an export when you want to retain
editable generation parameters.
