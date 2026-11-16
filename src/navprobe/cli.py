"""Terminal interface sharing the editor's scenario and simulation APIs."""

import argparse
import cmd
import json
from pathlib import Path
import shlex
import sys

from .scenarios import CIRCUITS, Corridor, LoopScenario, Scenario, DungeonScenario, MazeScenario
from .scenarios.library import (BUNDLED_DIRECTORY, ScenarioPreset, discover_presets,
                                load_preset, save_preset, user_scenario_directory)


def parser():
    root = argparse.ArgumentParser(prog="navprobe", description="NavProbe: randomized robot navigation testing. No arguments opens the interactive navprobe> prompt.",
                                   formatter_class=argparse.RawDescriptionHelpFormatter,
                                   epilog="""Usage:
  Terminal:           navprobe COMMAND [OPTIONS]
  Python module:      python -m navprobe COMMAND [OPTIONS]
  Inside navprobe>:   COMMAND [OPTIONS]  (omit navprobe)

Start here:
  list presets          Show available track presets.
  generate --help       Terrain, layouts, static obstacles, and XML export.
  run --help            Robot/controller selection, A*, and playback speed.
  scenario --help       Save, reload, and edit scenario JSON.

Optional installs: navprobe[gui] for editor/preview; navprobe[scenic] for sampling.
Dynamic obstacles, runtime monitoring, and automated campaigns are not available yet.

Python API: from navprobe import ScenarioOptions, create_scenario, RunOptions, open_simulation
Every scenario/run setting is available through these library services; see docs/api.md.

Interactive controls: status, stop, restart, exit.
Use help COMMAND inside the prompt, or COMMAND --help in either context.""")
    root.add_argument("--gui", action="store_true", help="open the desktop editor (requires navprobe[gui] and a desktop display)")
    commands = root.add_subparsers(dest="command")
    listing = commands.add_parser("list", help="list robots or scenario presets")
    listing.add_argument("kind", choices=("robots", "presets"), default="presets", nargs="?")
    listing.add_argument("--library", type=Path, default=user_scenario_directory(), help="user preset library directory (default: %(default)s); built-in presets are also searched")
    for action in ("run", "scenario", "preview", "generate"):
        item = commands.add_parser(action, help={"run": "launch a simulation (Ctrl+C stops it)", "scenario": "inspect, edit, export or save a scenario", "preview": "open a top-down track preview", "generate": "write an environment scene XML without launching the app"}[action])
        item.formatter_class = argparse.RawDescriptionHelpFormatter
        item.description = {
            "generate": "Generate ground, layout walls, and optional static objects, and export an environment-only MuJoCo scene. No GUI or simulation starts.",
            "run": "Run a robot on a generated track, or load an existing scene or experiment package.",
            "scenario": "Inspect or save editable scenario JSON, including concrete static-object placements when populated. Reload with --scenario. Use generate for MuJoCo XML.",
            "preview": "Open a top-down geometry preview, including static obstacles; requires navprobe[gui] and a desktop display. This does not compute the A* route.",
        }[action]
        examples = {
            "generate": """  generate --corridor 3 0 --corridor 2 90 --width 1.2 --output scene.xml
  generate --loop circle --radius 3 --terrain waves --height 0.02 --spacing 1 --output waves.xml
  generate --preset 04_zigzag --terrain random --seed 7 --resolution 257 --output bumps.xml
  generate --scenario my-track.json --width 1 --output custom.xml
  validate scene.xml
  run --scene scene.xml""",
            "run": """  run --preset 04_zigzag --robot simple_robot
  run --loop circle --terrain random --height 0.003 --seed 7
  run --scene scene.xml
  run --robot /path/to/robot.xml --no-auto-follow
  run --maze --static-objects 3 --navigation astar --simulation-speed 5
  run --scenario saved-maze.json --robot simple_robot
  run --package robot.zip --maze --trust-package""",
            "scenario": """  scenario --preset 04_zigzag
  scenario --corridor 3 0 --corridor 2 -90 --width 1.2 --output my-track.json
  scenario --scenario my-track.json --terrain random --seed 7 --name 'Bumpy track' --save
  scenario --maze --static-objects 3 --object-seed 9 --output saved-maze.json""",
            "preview": """  preview --preset 04_zigzag
  preview --loop figure_eight --radius 3""",
        }
        item.epilog = ("""Examples (inside navprobe>; prepend navprobe in a terminal):
""" + examples[action] + """

Dungeon example: generate --dungeon --rooms 6 --room-shape circular --layout-seed 7 --output scene.xml
Population example: generate --dungeon --static-objects 4 --object-seed 9 --robot simple_robot --output boxes.xml
A selected robot uses its initial-pose collision bounds plus --footprint-margin
(default 0.05 m). --robot-radius overrides inference. Without a selected robot,
generation preserves the saved radius or uses 0.3 m. Saved placements are checked
against the selected robot, not silently resampled; enlarge passages if rejected.
This checks planar circular-footprint connectivity, not dynamics or turning.
New box samples require navprobe[scenic]; saved concrete placements can be reloaded
without Scenic. Navigation placement targets the reference route while preserving
geometric connectivity for --robot-radius; it does not guarantee controller success.
With simple_robot, --navigation auto selects A* on flat dungeons, mazes, and
populated corridors/loops. Other robots and uneven tracks retain line following,
which does not avoid boxes. --no-auto-follow disables the bundled controller.
The black ground line is the reference route; the blue viewer overlay is the A*
plan. Dungeons and mazes use flat ground and known maps, without exploration.
Maze example: generate --maze --maze-algorithm prim --maze-rows 8 --maze-columns 10 --width 2 --cell-size 3 --layout-seed 7 --output maze.xml
Maze navigation: run --maze --maze-algorithm growing-tree --newest-probability 0.7 --loop-fraction 0.1 --simulation-speed 5
Mazes default to 8×8 cells, 3 m cell spacing, 2 m passages; flat ground only.
--loop-fraction opens extra connections after generation; 0 gives a perfect maze.
--newest-probability affects Growing Tree only. Static object flags apply to all generated layouts. Narrow tracks may need a larger --width.
Choose at most one source: --maze, --dungeon, --scenic, --preset, --scenario, --loop, or repeated --corridor.
Scenic samples flat ground, 2-8 corridors, one shared width, and relative turns.
Example: generate --scenic --scenic-seed 7 --output scene.xml
Scenic files execute code: use trusted sources only.
Without a source, the default is a straight 2 m corridor. Additional flags
replace selected preset/JSON settings; omitted flags retain those settings.
Corridors/loops default to width 0.8 m; dungeons default to 3 m passages, 8–16 m
rooms, and 200×200 m ground. Line width defaults to 0.025 m; terrain is flat.
Terrain settings affect waves/random only; --seed affects random bumps only.
Wall height (0.3 m) and thickness (0.02 m) are currently fixed.
""")
        if action == "generate":
            item.epilog += """
Exports contain no robot or controller. Uneven terrain also creates a sibling
<output-stem>_assets directory; keep it beside the XML. Output files/assets
must not already exist, and the parent directory must exist.
run --scene opens the exported environment for inspection. Use run with the
same track options and --robot to simulate a robot on the generated track.
"""
        if action == "scenario":
            item.epilog += """
Save once, then reuse the same populated environment:
  scenario --maze --static-objects 3 --output saved-maze.json
  run --scenario saved-maze.json --robot simple_robot
Unchanged saved placements are reused. Changing layout/population settings may
invalidate or resample placements. This saves an environment, not a complete run
record. Automatic test-case archiving and historical replay are outside scope.
"""
        if action == "run":
            item.epilog += """
--navigation, --grid-resolution, and --navigation-clearance apply to generated
layouts, not imported scenes or packages. Explicit A* requires simple_robot on
flat ground with automatic driving enabled. Grid/clearance options require A*.
Full experiment ZIPs supply their own environment; only robot ZIPs accept layout
options. --trust-package permits imported Python execution; it is not a sandbox.
--simulation-speed changes playback pacing only, not physics time or robot speed.
"""
        source = item.add_mutually_exclusive_group()
        source.add_argument("--scenic", type=Path, nargs="?", const=Path(__file__).parent / "scenarios/scenic/flat_corridors.scenic", help="sample a trusted Scenic file, or omit the path for bundled flat corridors; requires the scenic extra")
        item.add_argument("--scenic-seed", type=int, default=None, help="Scenic sampling seed (default: 42); requires --scenic; independent of terrain --seed")
        source.add_argument("--preset", help="preset file stem or exact display name; see list presets")
        source.add_argument("--scenario", type=Path, help="import a scenario JSON file")
        source.add_argument("--maze", action="store_true", help="generate a seeded grid maze on flat ground (default: 8 by 8, DFS)")
        item.add_argument("--maze-algorithm", choices=("dfs", "prim", "growing-tree"), help="DFS: winding passages; Prim: random frontier edges; Growing Tree: mixed active-cell policy")
        for option, kind, description in (
            ("maze-rows", int, "maze rows, 2–40 (default: 8)"),
            ("maze-columns", int, "maze columns, 2–40 (default: 8)"),
            ("cell-size", float, "maze cell-centre spacing in metres (default: 3); must exceed --width by >= 0.1; ground <= 200 m per side"),
            ("newest-probability", float, "Growing Tree probability of selecting newest active cell, 0–1 (default: 0.5); 1 matches DFS; 0 selects random active cells"),
            ("loop-fraction", float, "fraction of remaining grid connections to open, 0–1 (default: 0 = perfect maze); permits alternative routes"),
        ):
            item.add_argument("--" + option, type=kind, help=description)
        source.add_argument("--dungeon", action="store_true", help="generate a seeded BSP room-and-corridor dungeon on flat ground")
        for option, kind, description in (
            ("map-width", float, "dungeon ground width in metres (default: 200; maximum: 200)"),
            ("map-height", float, "dungeon ground height in metres (default: 200; maximum: 200)"),
            ("rooms", int, "BSP room count, 2 to 64 (default: 6; must fit bounds)"),
            ("room-min", float, "minimum room side/diameter in metres (default: 8)"),
            ("room-max", float, "maximum room side/diameter in metres (default: 16)"),
            ("layout-seed", int, "dungeon/maze layout seed, independent of terrain seed (default: 42)"),
        ):
            item.add_argument("--" + option, type=kind, help=description)
        item.add_argument("--room-shape", choices=("rectangular", "circular"), help="BSP room shape (default: rectangular); circular size is diameter")
        for option, kind, description in (
            ("static-objects", int, "fixed boxes in generated layouts, 0–30; Scenic placement (default: 0); 0 disables population"),
            ("object-seed", int, "Scenic placement seed, 0–2147483647; changing it leaves the layout fixed (default: 42)"),
            ("object-min-size", float, "minimum box width/length in metres, > 0 and <= maximum (default: 0.25)"),
            ("object-max-size", float, "maximum box width/length in metres, <= 3 (default: 0.6)"),
            ("object-height", float, "fixed box height in metres, > 0 and <= 3 (default: 0.4)"),
            ("robot-radius", float, "manual final footprint radius in metres, > 0; overrides automatic inference; without a robot use saved radius or 0.3; separate from A* clearance"),
            ("object-clearance", float, "minimum wall/object clearance in metres, 0–2 (default: 0.1)"),
        ):
            item.add_argument("--" + option, type=kind, help=description)
        item.add_argument("--footprint-margin", type=float, default=None, help="extra clearance added to inferred collision radius, metres >= 0 (default: 0.05); not added to manual --robot-radius")
        item.add_argument("--robot-body", help="root body name for footprint inference; required when the XML contains multiple robot trees")
        if action != "run":
            item.add_argument("--robot", help="robot key or XML used only to infer footprint for generation/preview/save; does not add a robot to exported XML")
        item.add_argument("--object-placement", choices=("navigation", "clear-route"),
                          help="navigation allows route/passage obstacles and targets the first box on the reference route; clear-route keeps the baseline route clear (default: navigation)")
        source.add_argument("--loop", choices=tuple(CIRCUITS), help="closed wall layout: circle or figure_eight; default radius/scale 2 m")
        source.add_argument("--corridor", nargs=2, type=float, action="append", metavar=("LENGTH", "TURN"), help="add a section: LENGTH > 0 metres, TURN in degrees (-180 < TURN < 180); first TURN must be 0; positive turns left, negative right; repeat in route order")
        item.add_argument("--width", type=float, help="usable corridor/track width in metres, excluding walls; must exceed line width (defaults: corridors/loops 0.8, dungeons 3, mazes 2)")
        item.add_argument("--line-width", type=float, help="painted center-line width in metres; > 0 and < track width (new-track default: 0.025)")
        item.add_argument("--radius", type=float, help="loop radius/scale in metres; requires a loop source and must be at least twice the track width (default: 2)")
        item.add_argument("--terrain", choices=("flat", "waves", "random"), help="ground surface: flat, smooth waves, or seeded random bumps (new-track default: flat)")
        item.add_argument("--height", type=float, help="terrain peak-to-valley height, 0 to 0.3 metres; 0.02 = 2 cm (default: 0.003; ignored for flat)")
        item.add_argument("--spacing", type=float, help="terrain wavelength, 0.1 to 10 metres; larger values give gentler slopes; random wavelengths range from this value to twice it (default: 0.8)")
        item.add_argument("--resolution", type=int, help="height samples along the longest ground dimension, integer 33 to 513 (default: 129); increase if the grid is too coarse")
        item.add_argument("--seed", type=int, help="random-bump seed, integer 0 to 2147483647 (default: 42); same track/settings/seed reproduce the same ground")
        item.add_argument("--library", type=Path, default=user_scenario_directory(), help="user preset library directory (default: %(default)s); built-in presets are also searched")
        if action == "generate":
            item.add_argument("--output", type=Path, default=Path("scene.xml"), help="new scene XML file (default: scene.xml)")
        if action == "scenario":
            item.add_argument("--name", help="display name for the exported/saved scenario; quote names containing spaces")
            item.add_argument("--description", help="description stored in exported/saved scenario JSON")
            item.add_argument("--save", action="store_true", help="save the configured scenario and concrete placements to --library")
            item.add_argument("--output", type=Path, help="export scenario JSON and concrete placements to a new file; parent directory must exist")
        if action == "run":
            item.add_argument("--navigation", choices=("auto", "line", "astar"), help="auto selects A* for simple_robot flat dungeons/mazes or populated tracks; otherwise line following")
            item.add_argument("--grid-resolution", type=float, help="A* grid spacing in metres (default: 0.25); finer grids resolve narrower passages")
            item.add_argument("--navigation-clearance", type=float, help="A* circular footprint plus tracking margin, >= 0.25 m (default: max(0.3, resolved footprint radius))")
            item.add_argument("--simulation-speed", type=float, default=1.0, help="playback multiplier, 0.1–20 (default: 1); changes pacing, not physical robot speed or timestep")
            model = item.add_mutually_exclusive_group()
            model.add_argument("--robot", default=None, help="registered robot key or custom XML path (default: simple_robot)")
            model.add_argument("--scene", type=Path, help="open existing XML unchanged; no robot or Python controller is added, including for environment-only exports")
            model.add_argument("--package", type=Path, help="full ZIP testing (environment, robot, controller) or robot/controller ZIP; mode detected automatically")
            item.add_argument("--auto-follow", action=argparse.BooleanOptionalAction, default=None, help="defaults to on for registered robots")
            item.add_argument("--menagerie", type=Path, help="local MuJoCo Menagerie directory for packages that require it; requires --package")
            item.add_argument("--run-directory", type=Path, help="working/output directory for full ZIP entry-point scripts")
            item.add_argument("--trust-package", action="store_true", help="explicitly permit the selected ZIP's Python code to run")
    validate = commands.add_parser("validate", help="validate scenario JSON, scene XML or experiment ZIP without running Python controllers")
    validate.add_argument("path", type=Path, help="scenario .json, complete scene .xml, or experiment .zip to validate")
    validate.add_argument("--menagerie", type=Path, help="local MuJoCo Menagerie directory if required by a ZIP package")
    return root


def catalog(directory):
    from .services import list_presets
    result = list_presets(directory)
    for error in result.errors:
        print(f"Warning: {error}", file=sys.stderr)
    return [(entry.path, entry.preset, entry.origin) for entry in result.entries]


def _report_footprint(preset, footprint, *, manual=False):
    if footprint or manual:
        source = f"inferred from {footprint.body}, includes {footprint.margin:g} m margin" if footprint else "manual override"
        print(f"Robot footprint: {preset.scenario.objects.robot_radius:.3f} m radius ({source})", file=sys.stderr)


def selected_preset(args, *, robot_path=None):
    from .services import ScenarioOptions, configure_scenario
    result = configure_scenario(ScenarioOptions.from_mapping(vars(args)), robot_path=robot_path)
    for warning in result.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    _report_footprint(result.preset, result.footprint, manual=args.robot_radius is not None)
    return result.preset


def worker_request(args):
    from .execution import RunOptions, prepare_run
    request = prepare_run(RunOptions.from_mapping(vars(args)))
    for warning in request.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    if request.preset:
        _report_footprint(request.preset, request.footprint, manual=args.robot_radius is not None)
    if request.run_directory:
        print(f"Full ZIP outputs: {request.run_directory / 'experiment'}")
    return request.worker_request()


# Compatibility for callers using these earlier interface helpers.
from .execution import start_worker, stop_simulation as stop_worker
from .interfaces import require_gui, preview_scenario as preview


def execute(args, shell=None):
    if args.gui:
        if args.command:
            raise ValueError("Use --gui without a CLI command.")
        from .interfaces import open_gui
        open_gui()
        return 0
    if args.command == "list":
        if args.kind == "robots":
            from .services import list_robots
            for robot in list_robots():
                print(f"{robot.key}\t{robot.label}\t{robot.path}")
        else:
            for path, preset, origin in catalog(args.library):
                print(f"{path.stem}\t{preset.name}\t{origin}\t{'maze' if isinstance(preset.scenario, MazeScenario) else 'dungeon' if isinstance(preset.scenario, DungeonScenario) else 'loop' if preset.scenario.closed else 'corridor'}")
    elif args.command == "generate":
        from .simulation.generation import export_scene
        preset = selected_preset(args)
        print(f"Generated: {export_scene(preset.scenario, args.output)}")
    elif args.command in ("scenario", "preview"):
        preset = selected_preset(args)
        if args.command == "preview":
            return preview(preset)
        if args.output:
            from .services import export_scenario
            export_scenario(preset, args.output)
            print(f"Exported: {args.output}")
        if args.save:
            print(f"Saved: {save_preset(preset, args.library.expanduser())}")
        if not args.save and not args.output:
            print(json.dumps(preset.to_dict(), indent=2, allow_nan=False))
    elif args.command == "validate":
        from .services import validate_input
        result = validate_input(args.path, menagerie=args.menagerie)
        if result.kind == "package":
            print(f"Valid package: {result.name} ({result.mode}); SHA-256: {result.digest}")
        elif result.kind == "scene":
            print("Valid MuJoCo scene")
        else:
            print(f"Valid scenario: {result.name}")
    elif args.command == "run":
        request = worker_request(args)
        if shell:
            stop_worker(shell.process)
            shell.process = start_worker(request)
            shell.last_request = request
            print("Simulation started. Use status, stop or restart; close the viewer to finish.")
        else:
            process = start_worker(request)
            try:
                return process.wait()
            except KeyboardInterrupt:
                stop_worker(process)
                return 130
    return 0


class SimulationShell(cmd.Cmd):
    intro = "NavProbe: robot navigation testing. Type help for commands, --gui to open the editor, or exit."
    prompt = "navprobe> "

    def __init__(self):
        super().__init__()
        self.process = None
        self.last_request = None
        self.argument_parser = parser()

    def emptyline(self):
        pass

    def default(self, line):
        try:
            args = self.argument_parser.parse_args(shlex.split(line))
            if not args.command and not args.gui:
                self.argument_parser.print_help()
            else:
                execute(args, self)
        except SystemExit as exc:
            # argparse help/errors must not close the shell; GUI exits also return here.
            if exc.code not in (None, 0, 2):
                print(f"Command exited: {exc.code}", file=sys.stderr)
        except (OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
        except KeyboardInterrupt:
            print("\nCommand interrupted.")

    def do_help(self, arg):
        """Show CLI help, or help for a command: help run."""
        if arg in ("stop", "restart", "status", "exit"):
            return super().do_help(arg)
        self.default(f"{arg} --help" if arg else "--help")
        if not arg:
            print("Interactive controls: status, stop, restart, exit. Re-run a run command to replace a simulation.")

    def do_stop(self, arg):
        """Stop the active simulation."""
        stop_worker(self.process)
        print("Simulation stopped.")

    def do_status(self, arg):
        """Report whether the worker is running or its exit status."""
        print("No simulation started." if self.process is None else
              "Simulation running." if self.process.poll() is None else
              f"Simulation exited with code {self.process.returncode}.")

    def do_restart(self, arg):
        """Restart the last simulation, or use restart OPTIONS to replace its run options."""
        if arg:
            self.default("run " + arg)
        elif self.last_request:
            stop_worker(self.process)
            self.process = start_worker(self.last_request)
        else:
            print("Run a simulation first.")

    def do_exit(self, arg):
        """Stop the worker and exit the CLI."""
        return True

    def do_EOF(self, arg):
        print()
        return True


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        if not sys.stdin.isatty():
            parser().print_help()
            return 0
        shell = SimulationShell()
        try:
            shell.cmdloop()
        except KeyboardInterrupt:
            print()
        finally:
            stop_worker(shell.process)
        return 0
    root = parser()
    args = root.parse_args(arguments)
    try:
        return execute(args)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
