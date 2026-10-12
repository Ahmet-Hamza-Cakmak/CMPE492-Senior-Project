"""Run MuJoCo outside the editor event loop so the editor remains responsive."""

import argparse
import json
import sys

from ..scenarios.library import parse_preset
from . import build_model, run


def main():
    parser = argparse.ArgumentParser(description="Internal MuJoCo viewer worker")
    parser.add_argument("--robot", required=True)
    parser.add_argument("--auto-follow", action="store_true")
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        scenario = parse_preset(payload).scenario
        model = build_model(args.robot, scenario)
        run(model, scenario, auto_follow=args.auto_follow, robot_path=args.robot)
    except Exception as exc:
        print(f"Cannot run simulation: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
