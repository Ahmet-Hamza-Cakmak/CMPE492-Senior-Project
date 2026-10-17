"""Run MuJoCo outside the editor event loop so the editor remains responsive."""

import argparse
import json
import sys
import signal

from ..scenarios.library import parse_preset
from . import build_model, load_scene, run


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
    args = parser.parse_args()
    def stop_worker(signum, frame):
        raise SystemExit(0)

    previous_handler = signal.signal(signal.SIGTERM, stop_worker)
    try:
        if args.package:
            if not args.approved_sha256:
                raise ValueError("Packaged Python requires explicit approval of the ZIP hash.")
            if args.auto_follow:
                raise ValueError("Packaged experiments use their declared controller.")
            from ..experiments import open_package
            from ..experiments.controllers import load_controller, place_robot
            with open_package(args.package, menagerie_directory=args.menagerie,
                              expected_digest=args.approved_sha256) as experiment:
                if experiment.menagerie and not args.menagerie:
                    raise ValueError("This experiment needs a local mujoco_menagerie directory.")
                if experiment.mode == "standalone":
                    from ..experiments import run_assignment
                    from ..scenarios.library import user_scenario_directory
                    import uuid
                    destination = args.run_directory or user_scenario_directory().parent / 'runs' / uuid.uuid4().hex
                    run_assignment(experiment, destination)
                    return 0
                scenario = parse_preset(json.load(sys.stdin)).scenario if experiment.mode == "robot" else None
                model = build_model(experiment.model_path, scenario) if scenario else load_scene(experiment.model_path)
                if scenario:
                    place_robot(model, experiment.spawn)
                controller, context = load_controller(experiment, scenario)
                run(model, scenario, controller=controller, context=context)
            return 0
        if args.scene:
            if args.auto_follow:
                raise ValueError("Automatic line following is unavailable for imported scenes.")
            run(load_scene(args.scene))
            return 0
        payload = json.load(sys.stdin)
        scenario = parse_preset(payload).scenario
        model = build_model(args.robot, scenario)
        run(model, scenario, auto_follow=args.auto_follow, robot_path=args.robot)
    except Exception as exc:
        print(f"Cannot run simulation: {exc}", file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
    return 0


if __name__ == "__main__":
    sys.exit(main())
