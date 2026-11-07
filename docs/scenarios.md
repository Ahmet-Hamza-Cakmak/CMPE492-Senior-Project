# Scenario generation and navigation

[Documentation index](README.md) · [Project README](../README.md)

Commands and source paths assume the repository root unless stated otherwise.

## Create a scenario

1. Choose **Simple two-wheel robot** or **Google Robot (mobile adaptation)**, or browse for a custom MJCF XML.
2. Choose a scenario category: **Corridor tracks** contains Straight line, Left turn, Right turn, and Zigzag; **Loop tracks** contains Circle circuit and Figure-eight circuit. **BSP dungeons** provides rooms and passages; **Grid mazes** provides DFS, Prim, and Growing Tree presets. Saved scenarios appear in their matching category.
3. For corridors, edit the section count, lengths, and relative turns. For loops, edit the radius/scale. Both types have editable track and line widths. The top-down preview updates immediately. Positive turns go left, negative turns go right; the first corridor starts at the origin facing +X.
4. Use **Save to library…** to keep your edited scenario, or **Import JSON…** to load a scenario file. Switching presets prompts before discarding unsaved edits.
5. Leave **Automatically follow the line** checked to drive a bundled robot, or uncheck it for manual control. Custom XML has no automatic controller.
6. Click **Open MuJoCo simulation**. The editor remains responsive while MuJoCo runs in its own process. After selecting another scenario or editing parameters, click **Restart with selected scenario** to replace the running simulation. Selecting a preset updates the preview immediately; it does not change an already running MuJoCo world until you restart. Close the viewer or click **Stop simulation** to finish.

The corridors have white floors, black center lines, and solid light-gray walls on both sides. Walls are 0.3 m high and 2 cm thick, outside the specified usable corridor width. Corridor starts and finishes remain open; loop walls join continuously around the circuit. Consecutive strips share endpoints and have filled round joins; the walls follow the combined outline so they do not block the connections at bends or intersections. The editor preview shows the same wall layout. Sharp turns and self-intersections are allowed; intersecting tracks can create ambiguous routes for a future controller. The black line is visual and does not affect wheel contact, while the walls have physical collision enabled.

## Scenario library

Presets are versioned JSON files, independent of the robot model and controller. Both example robots can run the bundled presets. You can use the form to make a custom track and save it under a new name; saving never overwrites a bundled preset.

Built-in scenarios live in [scenarios/presets/](../src/robo_sim_py/scenarios/presets/). To ship another corridor scenario, add a JSON file there using this format and reinstall (or use an editable install). No GUI registration or Python changes are required:

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

**Import JSON…** loads a file for the current session; use **Save to library…** to retain it between launches. Invalid scenario files are reported without preventing other presets from loading. Version 1 describes corridor tracks and remains supported unchanged. Version 2 supports the loop type described below. Version 3 supports seeded BSP dungeons. Other environment types, such as obstacle fields, would also need a new geometry builder.

[scenarios/library.py](../src/robo_sim_py/scenarios/library.py) handles validation, discovery, and persistence. [ui/editor.py](../src/robo_sim_py/ui/editor.py) manages the Qt editor, [ui/preview.py](../src/robo_sim_py/ui/preview.py) draws the schematic, and [simulation/__main__.py](../src/robo_sim_py/simulation/__main__.py) launches the separate MuJoCo process. The physics and controllers remain independent of the UI toolkit.

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

JSON/Python height uses **metres**; the GUI displays **centimetres**. In Python, pass `terrain=Terrain("random", height=0.003, spacing=0.8, resolution=129, seed=42)` to `Scenario` or `LoopScenario` (import `Terrain` from `robo_sim_py`). Generation and surface painting live in [simulation/terrain.py](../src/robo_sim_py/simulation/terrain.py).

The existing controllers were tuned for flat ground. The Google example can stall on slopes or at turns, even with small bumps; successful completion is not guaranteed. Terrain settings deliberately allow experiments beyond either robot's capabilities.

If bumps look flat, remember that the default 0.3 cm is only 3 mm. For a visual inspection, disable automatic driving and try 5–10 cm height with 0.8 m spacing, then click **Restart with selected scenario** (or open a new simulation). These larger bumps may be undrivable. The start patch remains level; inspect the surface farther along the track. Tall walls can obscure the road from low camera angles. Terrain uses oblique lighting to make slopes easier to distinguish.

## Scenic flat-corridor scenario

Install the optional integration in the Python environment used to run the app:

```bash
python -m pip install -e ".[scenic]"
```

The bundled [flat_corridors.scenic](../src/robo_sim_py/scenarios/scenic/flat_corridors.scenic)
models one family of environments: flat ground, 2–8 connected corridor sections,
a shared width sampled uniformly from 0.8–1.5 m, section lengths from 2–4 m,
and relative turns from -75 to +75 degrees. The first section always starts
along +X with a zero turn. **All sections in one sample share one width**,
matching the existing track geometry and editor. Different samples have different
widths; per-section widths are not implemented. Edit the Scenic distributions to
change this family. These constraints do not guarantee robot traversability or
prevent a route from crossing itself.

From a terminal:

```bash
python -m robo_sim_py generate --scenic --scenic-seed 7 --output scene.xml
python -m robo_sim_py scenario --scenic --scenic-seed 7 --output sampled-track.json
python -m robo_sim_py preview --scenic --scenic-seed 7
python -m robo_sim_py run --scenic --scenic-seed 7 --robot simple_robot
```

Inside `navprobe>`, omit `python -m robo_sim_py`. `--scenic` selects the bundled
file; `--scenic path/to/file.scenic` selects a custom trusted file following the
same parameter schema. It is mutually exclusive with other track sources.
Existing width/terrain flags can override sampled settings afterward, just as
for JSON presets; the bundled scenario itself always samples flat terrain.
`--scenic-seed` defaults to 42 and is separate from the ordinary terrain `--seed`.
Save sampled JSON for replay across Scenic versions, where seeded results may
change. Scenic source executes Python code; load only trusted files.

In the GUI's **Scenario** card, click **Sample Scenic flat corridors…** and enter
a sampling seed. The generated corridor count, width, lengths, turns, and flat
ground appear in the existing editable controls and preview. Sampling does not
start simulation. Use **Save to library…** to retain the sample, or the existing
simulation button to run it. Sampling again allows you to choose a new seed;
unsaved edits still require the existing discard confirmation.

The adapter in [scenic_adapter.py](../src/robo_sim_py/scenarios/scenic_adapter.py)
loads and samples Scenic through its Python API, validates the concrete
parameters, and constructs the same `ScenarioPreset` used elsewhere. There is
no intermediate JSON requirement. Its imports are lazy, so existing workflows
continue to work without Scenic installed. The `.scenic` file supplies parameters
rather than Scenic physical objects; ground/walls are built by the existing
MuJoCo pipeline. This corridor-parameter integration is separate from the dungeon object population described below.


## BSP dungeons: rectangular or circular rooms

BSP dungeons are an additional layout type, built entirely in Python. The generator
recursively partitions bounded ground, places one room in each final partition,
and connects sibling subtrees with axis-aligned L-shaped passages. Walls follow
the union of rooms and passages, so doorways remain open. Circular room boundaries
are approximated by short wall panels. This is a BSP room-and-corridor approach,
not an implementation of the paper's additional L-system corridor grammar.

Generate an environment without opening a viewer:

```bash
python -m robo_sim_py generate --dungeon --rooms 6 --room-shape circular --layout-seed 7 --output dungeon.xml
python -m robo_sim_py generate --dungeon --map-width 20 --map-height 16 --rooms 8 --room-min 2 --room-max 4 --width 1 --room-shape rectangular --layout-seed 12 --output rooms.xml
python -m robo_sim_py scenario --dungeon --room-shape circular --layout-seed 7 --output dungeon.json
python -m robo_sim_py preview --scenario dungeon.json
python -m robo_sim_py run --scenario dungeon.json --robot simple_robot
python -m robo_sim_py run --scene dungeon.xml
```

Inside `navprobe>`, omit `python -m robo_sim_py`. `--dungeon` is mutually exclusive
with other scenario sources. Dungeon settings can also override a saved dungeon
preset or JSON. `generate --help` describes all options.

| Setting | Meaning | Default |
| --- | --- | --- |
| `--map-width`, `--map-height` | Ground bounds in metres, up to 200 per side | 200 × 200 |
| `--rooms` | Requested room count, 2–64; must fit the bounds | 6 |
| `--room-shape` | `rectangular` or `circular` for all rooms | rectangular |
| `--room-min`, `--room-max` | Minimum/maximum side length, or diameter, in metres | 8, 16 |
| `--width` | Connecting passage width in metres; less than minimum room size | 3 |
| `--layout-seed` | Reproduces the BSP layout with unchanged settings | 42 |
| `--line-width` | Width of the baseline route marking in metres | 0.025 |

BSP splitting is seeded and must reserve room margins. Some combinations cannot
fit the requested number of rooms; validation explains how to enlarge bounds or
reduce room count/minimum size. Connectivity and ground containment are checked.
These checks do not guarantee that every robot can negotiate every doorway or
turn. Dungeons currently require **flat terrain**; waves/random bumps are rejected.
`--layout-seed` controls the layout; the existing `--seed` still refers to terrain.

In the GUI, select **BSP dungeons** in the Scenario category dropdown. Set the
room shape, count, size range, ground dimensions, passage width, and layout seed.
The preview updates with the room/corridor floor, walls, start, goal, and route.
Use **Save to library…** or **Import JSON…** to preserve and reload settings.
Changing category restores the existing corridor/loop and terrain controls.

The robot starts at the first room's center, normalized to `(0, 0)`. The goal is
a distant room in the BSP connection tree. The black line marks a precomputed
reference route along that tree; it is not necessarily the shortest route through
the final physical geometry. Bundled controllers can follow this known route as a
baseline; they do not autonomously explore or solve a dungeon. Generated physical
corridors may intersect and introduce additional shortcuts. XML exports contain
only the environment; use generated-track `run` with a robot for automatic
following, or import the XML just to inspect it. Optional Scenic static-box
population is described below; dungeon topology itself remains Python-generated.

Dungeon presets use version 3 JSON. They record map dimensions, room count, size
range, room shape, layout seed, passage/line widths, and flat terrain settings.
Versions 1 and 2 remain supported. In Python:

```python
from robo_sim_py import DungeonScenario
from robo_sim_py.simulation.generation import export_scene

scenario = DungeonScenario(room_shape="circular", room_count=6, layout_seed=7)
export_scene(scenario, "dungeon.xml")
```


## Static objects with Scenic

Corridors, loops, BSP dungeons, and mazes optionally include fixed, collidable
boxes. Python builds the layout first. [dungeon_static.scenic](../src/robo_sim_py/scenarios/scenic/dungeon_static.scenic)
then creates actual Scenic spatial objects in placement regions supplied by the
Python adapter. Scenic samples positions, orientations, and widths/lengths and
checks containment and conservative inter-object separation. A Python validator
checks the final rotated footprints as well. This is separate from the older
Scenic corridor-parameter example.

Install the optional dependency if needed:

```bash
python -m pip install -e ".[scenic]"
```

```bash
python -m robo_sim_py generate --dungeon --room-shape circular --layout-seed 7 --static-objects 4 --object-seed 12 --output populated.xml
python -m robo_sim_py scenario --dungeon --static-objects 4 --object-seed 12 --output populated.json
python -m robo_sim_py preview --scenario populated.json
python -m robo_sim_py run --scenario populated.json --robot simple_robot --no-auto-follow
python -m robo_sim_py generate --scenario populated.json --object-seed 13 --output another-population.xml
```

Inside `navprobe>`, omit `python -m robo_sim_py`.

| Option | Meaning | Default |
| --- | --- | --- |
| `--static-objects` | Exact number of fixed boxes, 0–30; 0 disables sampling | 0 |
| `--object-seed` | Scenic placement seed, independent of `--layout-seed` | 42 |
| `--object-min-size` | Minimum box width and length, metres | 0.25 |
| `--object-max-size` | Maximum box width and length, metres | 0.6 |
| `--object-height` | Fixed height of all boxes, metres | 0.4 |
| `--object-clearance` | Minimum wall and inter-box gap, metres | 0.1 |
| `--object-placement` | `navigation` (route/passage obstacles) or `clear-route` | navigation |
| `--robot-radius` | Radius used for navigation-mode connectivity checks, metres | 0.3 |

The default `--object-placement navigation` uses each layout’s walkable floor. It targets the first box onto the original reference route, forcing a
controller that follows that route to account for an obstacle. The remaining boxes
are sampled across available floor space. Walls and mission-anchor regions remain
protected. Open layouts use start/goal; loops use four quarter-lap anchors.
Scenic rejects samples that disconnect these anchors after shrinking
the floor and expanding obstacle footprints by `--robot-radius` (default 0.3 m).
This checks geometric reachability for a circular robot, not a vehicle's turning
constraints or controller performance. Set the radius to cover your robot footprint.
The dungeon reference route follows BSP connections; the maze reference route
follows its cell graph. These are not computed physical shortest paths.

Use `--object-placement clear-route` to protect a robot-radius band around the
marked route. Dungeons additionally reserve their connecting passages. This mode is useful with
the explicit baseline line-following mode. Automatic control now selects
obstacle-aware A* for the simple two-wheel robot on flat dungeons, mazes, and
populated corridors/loops; other robots and uneven tracks retain line following. `--no-auto-follow` starts without automatic driving.
See the navigation section below.

The enlarged default is **200 × 200 m ground, 8–16 m room sides/diameters,
and 3 m passages**. Large maps can mean long robot travel times; use explicit
smaller bounds and room sizes for quick experiments. Existing saved JSON retains
its explicit dimensions; new defaults do not resize previously saved scenes.
Box-to-box separation uses conservative bounding circles in Scenic.

In the GUI choose any generated layout and set the shared **Static boxes**, size, height,
clearance, **Robot clearance radius**, **Object placement**, and **Object seed (Scenic)** fields. Finish editing a field (Enter or
move focus) to update placement. The top-down preview shows brown boxes; the
simulation and exported XML contain the same fixed collision geometry. Zero
boxes preserves the original unpopulated workflow and does not require Scenic.

Changing the object seed retains the generated layout. Changing topology
or population settings causes resampling. Infeasible requests report an error
rather than silently dropping objects; sampling is limited to 2,000 attempts.
Reduce count/size/clearance or increase passage width/room sizes if placement fails.

Saved scenario JSON includes both object-generation settings and concrete box
placements. Reloading those placements validates them and does not require Scenic;
XML loading never needs Scenic. Version 3 dungeon files without object fields
remain supported. To replay across dependency versions, use the saved concrete
JSON rather than relying only on a seed. Static boxes are fixed world geometry,
not free bodies; they will not fall or roll. No dynamic agents are implemented.


For example, create a large navigation challenge:

```bash
python -m robo_sim_py generate --dungeon --static-objects 3 --object-placement navigation --robot-radius 0.3 --object-seed 7 --output navigation-challenge.xml
python -m robo_sim_py run --scene navigation-challenge.xml
```

In the GUI, newly selected **BSP dungeons** use the larger defaults. If a saved
preset is selected, set Ground width/height to 200, room sizes to 8–16, and Track
width to 3 to obtain the same scale. Choose Navigation challenge for route obstacles.


## Obstacle-aware navigation for the simple two-wheel robot

The simple robot uses **grid A*** automatically on flat dungeons, mazes, and
populated corridor/loop scenarios. Unpopulated corridors/loops retain their
existing line controllers. Other robots and uneven terrain retain the baseline.
You can explicitly choose `--navigation line` for the original baseline or
`--navigation astar` for flat-layout navigation. A* requires the registered
`simple_robot` model and a generated/saved flat scenario. An arbitrary imported
scene does not supply the required layout, start, and goal description.

```bash
python -m robo_sim_py run --dungeon --static-objects 3 --object-seed 7 --robot simple_robot --navigation astar --simulation-speed 5
python -m robo_sim_py run --scenario populated.json --navigation astar --grid-resolution 0.25 --navigation-clearance 0.3 --simulation-speed 5
```

For quicker experiments, use a smaller world and shorter routes:

```bash
python -m robo_sim_py run --dungeon --map-width 24 --map-height 20 --room-min 4 --room-max 7 --width 2 --static-objects 3 --navigation astar --simulation-speed 5
```

In the GUI, choose **Simple two-wheel robot**, **BSP dungeons**, and leave
**Automatically drive robot** checked. The **Controller** selector defaults to
**Automatic (A* on supported flat maps)**; it also offers explicit line following
and A*. **A* grid spacing**, **Navigation clearance**, and **Simulation playback**
are in the robot card. A zero/Auto clearance value uses the default described below.

The planner uses ideal knowledge of the saved floor/wall and static-box footprints.
It shrinks free floor and expands obstacles by a circular clearance radius, then
performs eight-neighbor A*. Complete grid edges are checked, preventing diagonal
corner cutting. Visibility-based simplification removes unnecessary waypoints
only when the entire shortcut remains inside the same inflated free space.
The planned path is shown **blue in the MuJoCo viewer**; the black floor line and
top-down preview remain the original reference route.

| Run option | Meaning | Default |
| --- | --- | --- |
| `--navigation` | `auto`, `line`, or `astar` | auto |
| `--grid-resolution` | Initial grid spacing in metres | 0.25 |
| `--navigation-clearance` | Robot footprint plus tracking margin; minimum 0.25 m | max(0.3, scenario object robot-radius) |
| `--simulation-speed` | Requested wall-clock playback multiplier, 0.1–20 | 1 |

Grid geometry is evaluated lazily instead of allocating a dense map of the whole
200×200 m ground. If a geometric connection exists but the initial grid misses
it, the planner retries up to four times with halved spacing, without reducing
clearance. Each search has a 500,000-node expansion limit. An unreachable goal,
node-budget exhaustion, or unresolved narrow gap produces an actionable error;
the robot is not sent through a known obstacle as a fallback. Grid search and
path simplification do not guarantee a globally shortest continuous-space route.

The existing differential-drive motor feedback follows the planned path. Its
**0.16 m/s target physical speed, torque limits, and physics timestep remain
unchanged**. This is a static global planner, not a perception system or dynamic
obstacle avoidance controller. External disturbances can still make the follower
stop as lost; the current planner does not continuously replan after disturbance.
Planner settings are run options rather than fields in scenario JSON.

### Faster simulation without increasing robot speed

`--simulation-speed 5` requests five simulation seconds per wall-clock second.
The viewer syncs at up to roughly 60 Hz, while control and physics still update
at every original physics step. Speed 1 remains the default. Accelerated playback
is best-effort and limited by CPU/rendering throughput; it does not alter physical
velocity limits or increase the integration timestep. The setting also works for
CLI scene imports and managed packages, but not standalone assignment scripts
which own their execution loop. GUI playback controls apply to generated robot
runs. Very large maps still mean long simulated travel distances, so the smaller
example above is useful when testing planner behavior.

## Grid mazes

Choose **Grid mazes** in the GUI. Select Randomized DFS, Randomized Prim, or
Growing Tree, then edit rows, columns, cell spacing, passage width, and layout
seed. Finish editing a maze field to update the preview. Save/import uses the
same scenario library as other layouts (maze JSON version 4).

```bash
# Export geometry without starting a viewer:
python -m robo_sim_py generate --maze --maze-algorithm prim --maze-rows 8 --maze-columns 10 --layout-seed 7 --output maze.xml
# A small simulation with the bundled simple robot and automatic A*:
python -m robo_sim_py run --maze --maze-algorithm dfs --maze-rows 4 --maze-columns 4 --simulation-speed 5
# Tunable Growing Tree, with some extra connections:
python -m robo_sim_py run --maze --maze-algorithm growing-tree --newest-probability 0.7 --loop-fraction 0.15 --simulation-speed 5
# Save an editable configuration:
python -m robo_sim_py scenario --maze --maze-algorithm prim --output maze.json
python -m robo_sim_py run --scenario maze.json
```

Inside `navprobe>`, omit `python -m robo_sim_py`. Use `generate --help` or
`run --help` for detailed options.

Defaults: 8 rows × 8 columns, 3 m cell-centre spacing, 2 m usable passages,
layout seed 42. Rows/columns are integers 2–40; overall ground is limited to
200 m per side. Cell spacing must exceed passage width by at least 0.1 m.
Mazes currently use flat ground and support the shared Scenic static-box population.
DFS uses an iterative stack; Prim samples frontier edges. Growing Tree selects
the newest active cell with the configured probability, otherwise a random
active cell (1 matches DFS, 0 is a random-active-cell policy, not necessarily
identical to edge-based Prim). The probability only affects Growing Tree.

A loop fraction of 0 produces a perfect maze; values up to 1 open that fraction
of the remaining neighbour connections (rounded down). Extra loops allow
alternative graph routes. Start is the first cell at (0,0); the goal is a
farthest cell by shortest graph distance, selected deterministically. The black
line marks that graph route; the simple robot's A* route is blue in MuJoCo.
Navigation uses the complete static map; this is not autonomous maze exploration.
Other registered robots retain their baseline follower. Importing only the XML
opens geometry; use the scenario JSON or generation flags to run navigation.

### Objects on mazes, corridors, loops, and uneven tracks

The same object flags work with every generated scenario:

```bash
python -m robo_sim_py run --maze --maze-rows 4 --maze-columns 4 --static-objects 3 --object-seed 7 --simulation-speed 5
python -m robo_sim_py run --corridor 8 0 --corridor 5 90 --width 2 --static-objects 3 --object-seed 7 --simulation-speed 5
python -m robo_sim_py run --loop circle --radius 5 --width 2 --static-objects 3 --object-seed 7 --simulation-speed 5
python -m robo_sim_py generate --corridor 6 0 --width 2 --terrain waves --height 0.02 --spacing 1.5 --static-objects 2 --output bumpy-boxes.xml
```

Default 0.8 m corridors may be too narrow for a box and a robot-sized detour;
use a wider track or smaller objects. Placement fails explicitly if the configured
constraints cannot be met. Zero boxes requires no Scenic. Older saved scenarios
without object fields remain supported. Concrete placements replay without Scenic.

For loops, quarter-lap anchors are protected and checked for mutual reachability;
A* connects them in order and the follower repeats the resulting closed route.
This does not assert a particular winding or exploration strategy at crossings.
On uneven terrain, fixed level boxes are positioned above a conservative local
terrain peak to prevent penetration and may bridge lower patches. Placement
reachability is planar; it does not certify 3D traversability. Automatic obstacle
avoidance remains limited to the simple robot on flat ground. Explicit line mode
may collide with boxes, which is a valid controller test outcome.
