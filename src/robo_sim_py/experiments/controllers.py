"""Controller lifecycle shared by packaged Python controllers and the viewer."""

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
from typing import Protocol


@dataclass(frozen=True)
class ControllerContext:
    root: Path
    config: dict
    scenario: object | None
    route: tuple | None
    route_path: Path | None


class Controller(Protocol):
    def reset(self, model, data, context: ControllerContext): ...
    def step(self, model, data, context: ControllerContext): ...
    def close(self): ...


def load_controller(experiment, scenario=None):
    """Call only inside the worker after approval of this exact ZIP's digest."""
    context = ControllerContext(experiment.root, experiment.config, scenario,
                                tuple(scenario.points()) if scenario is not None else None,
                                experiment.route_path)
    sys.path.insert(0, str(experiment.controller_path.parent))
    spec = importlib.util.spec_from_file_location('experiment_controller', experiment.controller_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    factory = getattr(module, 'create_controller', None)
    if not callable(factory):
        raise ValueError('Controller must export create_controller() returning an object with reset, step and close.')
    controller = factory()
    for name in ('reset', 'step', 'close'):
        if not callable(getattr(controller, name, None)):
            raise ValueError(f'Controller is missing {name}().')
    return controller, context


def place_robot(model, spawn):
    """Translate/yaw a single free base from its XML pose, including keyframes."""
    if not any(spawn):
        return
    import math
    import mujoco
    import numpy as np

    joints = np.flatnonzero(model.jnt_type == mujoco.mjtJoint.mjJNT_FREE)
    if len(joints) != 1:
        raise ValueError('Nonzero spawn requires a robot with exactly one free joint; otherwise set its pose in XML.')
    address = model.jnt_qposadr[joints[0]]
    x, y, z, yaw = spawn
    angle = math.radians(yaw)
    c, s = math.cos(angle), math.sin(angle)
    rotation = np.array([math.cos(angle/2), 0, 0, math.sin(angle/2)])
    for qpos in [model.qpos0, *model.key_qpos]:
        old_x, old_y = qpos[address:address+2]
        qpos[address:address+3] = [c*old_x-s*old_y+x, s*old_x+c*old_y+y, qpos[address+2]+z]
        result = np.empty(4)
        mujoco.mju_mulQuat(result, rotation, qpos[address+3:address+7].copy())
        qpos[address+3:address+7] = result


class BundledController:
    """Adapt existing robot followers to the same lifecycle as packaged controllers."""
    def __init__(self, robot_path):
        self.robot_path = robot_path

    def reset(self, model, data, context):
        from ..assets import create_controller
        self.follower = create_controller(self.robot_path, model, context.scenario)

    def step(self, model, data, context):
        self.follower.update(data)

    def close(self):
        pass
