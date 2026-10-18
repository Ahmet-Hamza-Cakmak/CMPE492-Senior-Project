"""Terminal interface sharing the editor's scenario and simulation APIs."""

import argparse
import cmd
from dataclasses import replace
import json
from pathlib import Path
import shlex
import subprocess
import sys
import uuid

from .scenarios import CIRCUITS, Corridor, LoopScenario, Scenario
from .scenarios.library import (BUNDLED_DIRECTORY, ScenarioPreset, discover_presets,
                                load_preset, save_preset, user_scenario_directory)


def parser():
    root = argparse.ArgumentParser(prog="robo-sim-py", description="Robot simulation CLI. No arguments opens the interactive robo-sim> prompt.",
                                   formatter_class=argparse.RawDescriptionHelpFormatter,
                                   epilog="""Usage:
  Terminal:           python -m robo_sim_py COMMAND [OPTIONS]
  Inside robo-sim>:   COMMAND [OPTIONS]  (omit python -m robo_sim_py)

Start here:
  list presets          Show available track presets.
  generate --help       Ground, wall layout, and XML export options.
  run --help            Simulation and robot options.

Interactive controls: status, stop, restart, exit.
Use help COMMAND inside the prompt, or COMMAND --help in either context.""")
    root.add_argument("--gui", action="store_true", help="open the desktop editor")
    commands = root.add_subparsers(dest="command")
    listing = commands.add_parser("list", help="list robots or scenario presets")
    listing.add_argument("kind", choices=("robots", "presets"), default="presets", nargs="?")
    listing.add_argument("--library", type=Path, default=user_scenario_directory(), help="user preset library directory (default: %(default)s); built-in presets are also searched")
    for action in ("run", "scenario", "preview", "generate"):
        item = commands.add_parser(action, help={"run": "launch a simulation (Ctrl+C stops it)", "scenario": "inspect, edit, export or save a scenario", "preview": "open a top-down track preview", "generate": "write an environment scene XML without launching the app"}[action])
        item.formatter_class = argparse.RawDescriptionHelpFormatter
        item.description = {
            "generate": "Generate ground, then corridor/loop walls, and export an environment-only MuJoCo scene. No GUI or simulation starts.",
            "run": "Run a robot on a generated track, or load an existing scene or experiment package.",
            "scenario": "Inspect or export editable scenario JSON, or save it in the preset library. This does not export MuJoCo XML; use generate for XML.",
            "preview": "Open a top-down preview of the selected track layout.",
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
  run --robot /path/to/robot.xml --no-auto-follow""",
            "scenario": """  scenario --preset 04_zigzag
  scenario --corridor 3 0 --corridor 2 -90 --width 1.2 --output my-track.json
  scenario --scenario my-track.json --terrain random --seed 7 --name 'Bumpy track' --save""",
            "preview": """  preview --preset 04_zigzag
  preview --loop figure_eight --radius 3""",
        }
        item.epilog = ("""Examples (inside robo-sim>; prepend python -m robo_sim_py in a terminal):
""" + examples[action] + """

Choose at most one source: --preset, --scenario, --loop, or repeated --corridor.
Without a source, the default is a straight 2 m corridor. Additional flags
replace selected preset/JSON settings; omitted flags retain those settings.
New tracks default to width 0.8 m, line width 0.025 m, and flat terrain.
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
        source = item.add_mutually_exclusive_group()
        source.add_argument("--preset", help="preset file stem or exact display name; see list presets")
        source.add_argument("--scenario", type=Path, help="import a scenario JSON file")
        source.add_argument("--loop", choices=tuple(CIRCUITS), help="closed wall layout: circle or figure_eight; default radius/scale 2 m")
        source.add_argument("--corridor", nargs=2, type=float, action="append", metavar=("LENGTH", "TURN"), help="add a section: LENGTH > 0 metres, TURN in degrees (-180 < TURN < 180); first TURN must be 0; positive turns left, negative right; repeat in route order")
        item.add_argument("--width", type=float, help="usable corridor/track width in metres, excluding walls; must exceed line width (new-track default: 0.8)")
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
            item.add_argument("--save", action="store_true", help="add to the scenario library")
            item.add_argument("--output", type=Path, help="export JSON to a new file")
        if action == "run":
            model = item.add_mutually_exclusive_group()
            model.add_argument("--robot", default=None, help="registered robot key or custom XML path (default: simple_robot)")
            model.add_argument("--scene", type=Path, help="load a complete scene unchanged")
            model.add_argument("--package", type=Path, help="full, robot or assignment ZIP; mode detected automatically")
            item.add_argument("--auto-follow", action=argparse.BooleanOptionalAction, default=None, help="defaults to on for registered robots")
            item.add_argument("--menagerie", type=Path, help="local MuJoCo Menagerie directory for packages that require it; requires --package")
            item.add_argument("--run-directory", type=Path, help="retained assignment output directory")
            item.add_argument("--trust-package", action="store_true", help="explicitly permit the selected ZIP's Python code to run")
    validate = commands.add_parser("validate", help="validate scenario JSON, scene XML or experiment ZIP without running Python controllers")
    validate.add_argument("path", type=Path, help="scenario .json, complete scene .xml, or experiment .zip to validate")
    validate.add_argument("--menagerie", type=Path, help="local MuJoCo Menagerie directory if required by a ZIP package")
    return root


def catalog(directory):
    entries = []
    for folder, origin in ((BUNDLED_DIRECTORY, "built-in"), (directory, "saved")):
        presets, errors = discover_presets(Path(folder).expanduser())
        entries.extend((path, preset, origin) for path, preset in presets)
        for error in errors:
            print(f"Warning: {folder}: {error}", file=sys.stderr)
    return entries


def selected_preset(args):
    if args.scenario:
        preset = load_preset(args.scenario.expanduser())
    elif args.preset:
        matches = [preset for path, preset, _ in catalog(args.library)
                   if args.preset in (path.stem, preset.name)]
        if len(matches) != 1:
            raise ValueError("Preset must match exactly one name or file stem; use 'list presets'.")
        preset = matches[0]
    else:
        scenario = (LoopScenario(args.loop) if args.loop else
                    Scenario(tuple(Corridor(*part) for part in args.corridor)) if args.corridor else
                    Scenario((Corridor(2),)))
        preset = ScenarioPreset("Custom track", "", scenario)
    scenario = preset.scenario
    updates = {key: getattr(args, key) for key in ("width", "line_width", "radius") if getattr(args, key) is not None}
    if "radius" in updates and not scenario.closed:
        raise ValueError("--radius requires a loop scenario.")
    terrain = {key: getattr(args, option) for key, option in
               (("mode", "terrain"), ("height", "height"), ("spacing", "spacing"),
                ("resolution", "resolution"), ("seed", "seed")) if getattr(args, option) is not None}
    updates["terrain"] = replace(scenario.terrain, **terrain)
    scenario = replace(scenario, **updates)
    return ScenarioPreset(getattr(args, "name", None) or preset.name,
                          preset.description if getattr(args, "description", None) is None else args.description, scenario)


def worker_request(args):
    """Validate requests before starting or replacing a worker."""
    from .assets import EXAMPLES, example_for_path
    arguments = ["-m", "robo_sim_py.simulation"]
    payload = b""
    track_options = ("preset", "scenario", "loop", "corridor", "width", "line_width", "radius",
                     "terrain", "height", "spacing", "resolution", "seed")
    if args.scene or args.package:
        if args.auto_follow is not None:
            raise ValueError("--auto-follow/--no-auto-follow applies only to generated tracks with a robot.")
    if not args.package and (args.trust_package or args.menagerie or args.run_directory):
        raise ValueError("Package options require --package.")
    if args.scene:
        if any(getattr(args, option) is not None for option in track_options):
            raise ValueError("Track options cannot modify an imported scene.")
        path = args.scene.expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Scene does not exist: {path}")
        arguments.extend(["--scene", str(path)])
    elif args.package:
        from .experiments import open_package
        path = args.package.expanduser().resolve()
        with open_package(path, menagerie_directory=args.menagerie) as experiment:
            if experiment.menagerie and not args.menagerie:
                raise ValueError("This package requires --menagerie DIRECTORY.")
            if experiment.mode != "robot" and any(getattr(args, option) is not None for option in track_options):
                raise ValueError("Only robot packages accept generated track options.")
            if not args.trust_package:
                raise ValueError(f"Package '{experiment.name}' contains Python code that can access your files and network. "
                                 f"SHA-256: {experiment.digest}. Inspect it, then use --trust-package if you trust it.")
            arguments.extend(["--package", str(path), "--approved-sha256", experiment.digest])
            if args.menagerie:
                arguments.extend(["--menagerie", str(args.menagerie.expanduser().resolve())])
            if args.run_directory and experiment.mode != "standalone":
                raise ValueError("--run-directory is only supported for standalone assignment packages.")
            if experiment.mode == "standalone":
                destination = args.run_directory or user_scenario_directory().parent / "runs" / uuid.uuid4().hex
                destination = destination.expanduser().resolve()
                arguments.extend(["--run-directory", str(destination)])
                print(f"Assignment outputs: {destination / 'assignment'}")
            if experiment.mode == "robot":
                payload = json.dumps(selected_preset(args).to_dict(), allow_nan=False).encode()
    else:
        robot = next((example.path for example in EXAMPLES if example.key == (args.robot or "simple_robot")),
                     Path(args.robot or "simple_robot").expanduser()).resolve()
        if not robot.is_file():
            raise ValueError(f"Robot does not exist: {robot}. Use 'list robots' for registered keys.")
        automatic = args.auto_follow if args.auto_follow is not None else example_for_path(robot) is not None
        if automatic and example_for_path(robot) is None:
            raise ValueError("Automatic driving requires a registered robot; use --no-auto-follow for custom XML.")
        arguments.extend(["--robot", str(robot)])
        if automatic:
            arguments.append("--auto-follow")
        payload = json.dumps(selected_preset(args).to_dict(), allow_nan=False).encode()
    executable = str(Path(sys.executable).with_name("mjpython")) if sys.platform == "darwin" else sys.executable
    return [executable, *arguments], payload


def start_worker(request):
    arguments, payload = request
    process = subprocess.Popen(arguments, stdin=subprocess.PIPE)
    try:
        process.stdin.write(payload)
        process.stdin.close()
    except BrokenPipeError:
        pass
    return process


def stop_worker(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def preview(preset):
    from PySide6.QtWidgets import QApplication
    from .ui.preview import TrackPreview
    app = QApplication.instance() or QApplication(["robo-sim-py preview"])
    window = TrackPreview()
    window.setWindowTitle(preset.name)
    window.resize(800, 600)
    window.set_scenario(preset.scenario)
    window.show()
    return app.exec()


def execute(args, shell=None):
    if args.gui:
        if args.command:
            raise ValueError("Use --gui without a CLI command.")
        from .ui.editor import main as gui_main
        gui_main(["robo-sim-py"])
        return 0
    if args.command == "list":
        if args.kind == "robots":
            from .assets import EXAMPLES
            for robot in EXAMPLES:
                print(f"{robot.key}\t{robot.label}\t{robot.path}")
        else:
            for path, preset, origin in catalog(args.library):
                print(f"{path.stem}\t{preset.name}\t{origin}\t{'loop' if preset.scenario.closed else 'corridor'}")
    elif args.command == "generate":
        from .simulation.generation import export_scene
        preset = selected_preset(args)
        print(f"Generated: {export_scene(preset.scenario, args.output)}")
    elif args.command in ("scenario", "preview"):
        preset = selected_preset(args)
        if args.command == "preview":
            return preview(preset)
        if args.output:
            with args.output.expanduser().open("x", encoding="utf-8") as file:
                json.dump(preset.to_dict(), file, indent=2, allow_nan=False)
                file.write("\n")
            print(f"Exported: {args.output}")
        if args.save:
            print(f"Saved: {save_preset(preset, args.library.expanduser())}")
        if not args.save and not args.output:
            print(json.dumps(preset.to_dict(), indent=2, allow_nan=False))
    elif args.command == "validate":
        path = args.path.expanduser()
        if path.suffix.lower() == ".zip":
            from .experiments import open_package
            with open_package(path, menagerie_directory=args.menagerie) as experiment:
                print(f"Valid package: {experiment.name} ({experiment.mode}); SHA-256: {experiment.digest}")
        elif path.suffix.lower() == ".xml":
            from .simulation import load_scene
            load_scene(path)
            print("Valid MuJoCo scene")
        else:
            preset = load_preset(path)
            print(f"Valid scenario: {preset.name}")
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
    intro = "Robot simulation CLI. Type help for commands, --gui to open the editor, or exit."
    prompt = "robo-sim> "

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
