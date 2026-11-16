"""Run MuJoCo outside the editor event loop so the editor remains responsive."""

import argparse
import json
import sys
import signal

from ..scenarios.library import parse_preset
from ..execution import RunOptions, RunRequest, run_experiment
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Internal MuJoCo viewer worker")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--robot")
    source.add_argument("--scene")
    source.add_argument("--package")
    parser.add_argument("--approved-sha256")
    parser.add_argument("--menagerie")
    parser.add_argument("--run-directory")
    parser.add_argument("--auto-follow", action="store_true")
    parser.add_argument("--navigation", choices=("auto", "line", "astar"), default="auto")
    parser.add_argument("--grid-resolution", type=float, default=.25)
    parser.add_argument("--navigation-clearance", type=float)
    parser.add_argument("--simulation-speed", type=float, default=1.)
    args = parser.parse_args()
    def stop_worker(signum, frame):
        raise SystemExit(0)

    previous_handler = signal.signal(signal.SIGTERM, stop_worker)
    try:
        options = RunOptions(robot=args.robot, scene=args.scene, package=args.package,
            auto_follow=args.auto_follow if args.robot else None,
            navigation=args.navigation if args.robot else None,
            grid_resolution=args.grid_resolution if args.robot else None,
            navigation_clearance=args.navigation_clearance if args.robot else None,
            simulation_speed=args.simulation_speed, menagerie=args.menagerie,
            trust_package=bool(args.approved_sha256), approved_sha256=args.approved_sha256,
            run_directory=args.run_directory)
        preset = None
        mode = None
        if args.package:
            if not args.approved_sha256:
                raise ValueError("Packaged Python requires explicit approval of the ZIP hash.")
            if args.auto_follow:
                raise ValueError("Packaged experiments use their declared controller.")
            from ..experiments import open_package
            with open_package(args.package, menagerie_directory=args.menagerie,
                              expected_digest=args.approved_sha256) as experiment:
                mode = experiment.mode
                if experiment.menagerie and not args.menagerie:
                    raise ValueError("This experiment needs a local mujoco_menagerie directory.")
                if mode == "robot":
                    preset = parse_preset(json.load(sys.stdin))
        elif args.robot:
            preset = parse_preset(json.load(sys.stdin))
        elif args.auto_follow:
            raise ValueError("Automatic line following is unavailable for imported scenes.")
        request = RunRequest(options, preset=preset,
            robot_path=Path(args.robot) if args.robot else None,
            scene_path=Path(args.scene) if args.scene else None,
            package_path=Path(args.package) if args.package else None,
            package_mode=mode, approved_sha256=args.approved_sha256,
            run_directory=Path(args.run_directory) if args.run_directory else None,
            automatic=args.auto_follow)
        run_experiment(request)
    except Exception as exc:
        print(f"Cannot run simulation: {exc}", file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
    return 0


if __name__ == "__main__":
    sys.exit(main())
