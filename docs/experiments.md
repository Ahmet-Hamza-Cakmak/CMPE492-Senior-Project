# Experiment packages and extensions

The source selector supports:

| Choice | Environment | Robot and controller |
| --- | --- | --- |
| Built-in experiments / generated tracks | Adjustable corridor or registered loop, with flat/waves/random terrain | Bundled robot/controller, or a custom XML without automatic control |
| Assignment / full experiment ZIP | The assignment script builds it, or a manifest declares a complete scene | Script owns the simulation; manifest packages use the controller API |
| Robot + controller ZIP on generated track | The circuit and terrain selected in the editor | Package's robot-only XML and Python controller |
| Import MuJoCo scene XML | Complete XML loaded as supplied | Whatever the scene includes; no Python controller is loaded |

Changing modes preserves the current generated-track settings. Click Open/Restart to apply changes to a running simulation. JSON Save/Import remains a **track** library, not an experiment or controller library.

## Standard assignment submissions: no manifest required

ZIP filenames and their enclosing folder names are unrestricted by convention: `submission.zip`, `my test.zip`, or any other filesystem-valid name works. Detection uses the files inside, not an `A2-...` naming pattern. Place `python/main.py`, `scenes/` (containing at least one XML), and optional `data/` at the ZIP root or inside a single enclosing folder.

Choose **Assignment / full experiment ZIP**. Without `experiment.json`, the app runs `python/main.py` as `__main__` from the assignment root. The script owns scene/robot assembly, controls, the viewer, stepping, and telemetry. No `create_controller()` adapter or commands JSON is required. Sibling Python imports work. The standard entry point is launched without command-line arguments; scripts requiring extra mandatory arguments need suitable defaults or adaptation.

If the script uses Menagerie, select your local checkout in the optional folder field. For this mode it is made available both as `mujoco_menagerie/` within the working directory and as a sibling of the assignment root. This supports both the provided starter's relative paths and scripts resolving the checkout from `__file__`. The app does not guess the robot or rewrite the script.

Each standalone run receives a new persistent directory under the application's data directory (`~/.local/share/line-tracker-sim/runs/` on Linux by default, respecting `XDG_DATA_HOME`). The extracted assignment and any files the script writes there are retained after success, failure or Stop. The editor displays the run's assignment directory when the worker finishes. The original ZIP stays unchanged. You can remove old run folders when no longer needed. Because submissions can include large telemetry files, each retained run uses additional disk space.

When `experiment.json` **is present**, its explicit manifest configuration takes precedence and the managed full/robot controller API below applies. It remains required for robot-only packages to be driven on an app-generated track; a standalone script cannot automatically have its environment replaced.

## Try the examples

From the repository root:

```bash
python examples/make_packages.py
python -m robo_sim_py
```

Select **Robot + controller ZIP on generated track** and browse to `examples/A2-robot-demo.zip`. Start with a flat straight corridor. This controller uses the known reference route and the supplied simple robot's existing follower.

Select **Full experiment ZIP** and browse to `examples/A2-full-demo.zip`. This example runs a short fixed wheel-torque sequence in an enclosed scene. It does not follow a line or complete a lap. It applies zero torque after the sequence, which allows coasting rather than active braking.

Read the source before accepting the controller trust prompt. Stop closes the worker independently of the editor. The editor sends a termination request, then force-stops an unresponsive worker. For managed manifest packages, normal close, Python exceptions and graceful termination call `close()` and remove the temporary extraction. Forced termination cannot guarantee controller cleanup. For managed manifest packages, files written inside the extracted package are temporary; save any intended results to an explicitly chosen external location. Standard standalone assignments instead retain their run directory as described above.

## ZIP layout

```text
A2-name-surname/
├── experiment.json
├── python/
│   ├── main.py
│   └── helpers.py              # Optional supporting modules
├── scenes/
│   └── circuit.xml             # Full mode only
├── robots/
│   ├── robot.xml               # Robot mode, or included by the full scene
│   └── assets/
└── data/
    └── reference.json          # Optional controller inputs
```

ZIP the assignment folder or its contents. If provided, the manifest must be at the ZIP root or immediately inside one enclosing folder. Include all required files except a separately selected Menagerie checkout. XML assets/includes retain their relative structure. Source files are never rewritten.

ZIP validation rejects traversal paths, symlinks/special files, duplicate paths, encrypted archives, ambiguous manifests, and packages exceeding 256 MiB compressed, 1 GiB expanded, or 10,000 entries. Validation inspects data only; it does not import Python. XML syntax and referenced asset loading are checked by MuJoCo in the worker, and failures are displayed in the editor.

## Optional manifest: version 1

A robot-only experiment:

```json
{
  "version": 1,
  "name": "My robot experiment",
  "mode": "robot",
  "robot": "robots/robot.xml",
  "controller": "python/main.py",
  "config": {"speed": 0.15},
  "spawn": [0, 0, 0, 0],
  "menagerie": false
}
```

For a full experiment, change `"mode"` to `"full"` and replace `"robot"` with `"scene": "scenes/circuit.xml"`. The full scene includes any robots itself. Do not supply both `scene` and `robot`.

Required fields: `version`, `name`, `mode`, `controller`, and either `scene` or `robot`. Optional fields:

- `config`: a JSON object passed directly to the controller. The controller validates its own settings.
- `route`: package-relative path to optional data (e.g. `data/reference.json`). The app passes the path, without assuming a data format. Additional inputs can be declared in `config` and resolved against `context.root`.
- `spawn`: `[x_offset, y_offset, z_offset, yaw_degrees]`, metres/degrees, default all zero. Robot mode rotates the XML's free-base position about the world origin and adds the translation; orientation gets the same yaw. A nonzero spawn requires exactly one free joint and also transforms stored keyframe poses. Robots with planar joints should specify placement directly in XML. Full experiments set their poses in the scene XML. Placement is not collision-checked; select a feasible pose for the chosen track.
- `menagerie`: Boolean indicating an external local checkout is required.

Fields `robot`, `scene`, `controller`, and `route` must name files inside the package. Unknown manifest fields are rejected so misspelled settings do not silently take effect. This manifest is separate from the scenario JSON formats.

## Controller API

`python/main.py` exports `create_controller()` returning an object with these methods:

```python
class Controller:
    def reset(self, model, data, context):
        # Called at startup and when simulation time moves backward (viewer reset).
        self.motor = model.actuator("left_motor").id

    def step(self, model, data, context):
        # Called before every physics step; set actuator commands here.
        data.ctrl[self.motor] = 0.0

    def close(self):
        # Release resources. Called even when reset/step raises an exception.
        pass


def create_controller():
    return Controller()
```

The app owns `MjData`, stepping, timing and the viewer. A standalone assignment script that creates its own viewer/loop must be adapted to this interface. Each worker imports one controller; regular sibling imports such as `import helpers` are supported. Relative package imports should use a normal subpackage under `python/`.

`context` provides:

| Attribute | Value |
| --- | --- |
| `root` | `Path` to the extracted assignment root |
| `config` | Manifest's controller settings |
| `scenario` | Generated scenario object for robot mode; `None` for full mode |
| `route` | Ordered XY centreline tuple for generated tracks; `None` for full mode |
| `route_path` | Optional input file named by the manifest's `route`; otherwise `None` |

Controllers may use the known route, MuJoCo sensor data, or a fixed sequence of commands. Receiving a route does not require using it. No sensor simulation or perception capability is added automatically. Controllers must match their robot's actuators and dynamics. Python dependencies must already be installed in the app's environment; packages do not automatically install requirements.

## Trust and local dependencies

Imported Python has your user's file/network permissions. The separate process keeps the editor responsive and allows stopping, but **is not a security sandbox**. The app asks for trust on each launch and binds approval to the ZIP's SHA-256 hash; the worker rejects a ZIP changed since approval. The hash identifies bytes, not authorship or safety.

For managed manifest packages, set `"menagerie": true` and select your local `mujoco_menagerie` folder. The chooser remembers that path. The app places a temporary sibling link to it, matching the assignment layout:

```text
<temporary root>/
├── mujoco_menagerie/            # Link to your local checkout
└── experiment/
    ├── scenes/circuit.xml
    └── ...
```

For an XML in `scenes/`, a reference such as `../../mujoco_menagerie/google_robot/robot.xml` reaches that checkout. Keep model-specific compiler asset directories consistent with MuJoCo's relative-path rules. No checkout is downloaded or copied. Creating the link requires symlink support (on Windows, Developer Mode or suitable privileges may be needed). Dependencies outside the ZIP are not covered by its hash.

## Adding built-in robots and circuits later

No Hello Stretch 3 or Monte Carlo model is added by this change.

**Robot:** keep the XML, assets and controller together. Add a `RobotExample` in `assets/__init__.py`, or call `register_robot(...)` before constructing the editor. Each entry includes key, display label, controller factory, optional explicit model path, and optional spawn offset. Existing follower factories take `(model, scenario)` and expose `update(data)`; the built-in adapter supplies the shared reset/step/close lifecycle. To reuse an API-v1 packaged controller as a built-in follower, provide a small adapter from these factory/update methods. The dropdown discovers entries from this registry. Include any new asset formats in package-data settings.

**Circuit:** `scenarios.CIRCUITS` maps shape keys to `CircuitDefinition(label, size_label, generate)`. A generator receives the radius/scale in metres and returns finite XY points around one closed loop. Do not repeat consecutive points. The app aligns its first point to the origin and first segment to +X, closes the route, and applies shared walls, terrain, start markings and preview. Register via `register_circuit(key, definition)`, then add a version-2 loop preset using that key. Install registrations in application code before the editor or worker loads presets; a registration only made in the GUI process will not propagate to workers. ZIPs do not execute registration hooks. Existing geometry validation requires a scale at least twice the track width.

More complex circuit parameters, bridges or separate elevation layers would require extending the scenario schema/builder; the current registry is for planar closed routes with one size parameter. New corridor layouts need only a JSON preset.

Implementation lives in `experiments/` (package validation and controller API), `simulation/` (model construction and execution), and the existing asset/scenario registries. The editor delegates execution to a fresh worker, preserving the old built-in and direct-XML workflows.
