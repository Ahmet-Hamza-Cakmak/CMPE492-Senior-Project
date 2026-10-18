"""Load robot assets in place and add connected track geometry."""

from pathlib import Path
import time

from ..scenarios import Scenario


def example_robot(name="simple_robot"):
    from ..assets import EXAMPLES
    for example in EXAMPLES:
        if example.key == name:
            return example.path
    raise ValueError(f"Unknown example robot: {name}")


def load_scene(scene_path):
    """Load a complete scene in place, preserving includes, assets and settings."""
    import mujoco

    path = Path(scene_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Scene XML does not exist: {path}")
    return mujoco.MjModel.from_xml_path(str(path))


def build_model(robot_path, scenario: Scenario, *, pipeline=None):
    import mujoco

    path = Path(robot_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Robot XML does not exist: {path}")
    # Loading from the original location preserves relative includes and assets.
    spec = mujoco.MjSpec.from_file(str(path))
    from .generation import GenerationPipeline
    (pipeline or GenerationPipeline()).build(spec, scenario)
    model = spec.compile()
    from ..assets import example_for_path
    example = example_for_path(path)
    if example is not None and any(example.spawn):
        from ..experiments.controllers import place_robot
        place_robot(model, example.spawn)
    return model


def run(model, scenario=None, *, auto_follow=False, robot_path=None, controller=None, context=None):
    import mujoco
    import mujoco.viewer

    if auto_follow and scenario is None:
        raise ValueError("Automatic line following requires a generated scenario.")
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    from ..experiments.controllers import BundledController, ControllerContext
    if auto_follow:
        if controller is not None:
            raise ValueError("Choose either a packaged controller or the built-in controller.")
        path = Path(robot_path or example_robot())
        controller = BundledController(path)
        context = ControllerContext(path.parent, {}, scenario, tuple(scenario.points()), None)
    managed = context is not None and controller is not None
    previous_time = float(data.time)
    try:
        if managed:
            controller.reset(model, data, context)
            mujoco.mj_forward(model, data)
        with mujoco.viewer.launch_passive(model, data) as viewer:
            if scenario is not None:
                xs, ys = zip(*scenario.points())
                viewer.cam.lookat[:] = [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 0]
                viewer.cam.distance = max(max(xs) - min(xs), max(ys) - min(ys), scenario.width) * 1.6 + 1
                viewer.cam.elevation = -80 if scenario.terrain.mode != "flat" else -65
            else:
                mujoco.mjv_defaultFreeCamera(model, viewer.cam)
            while viewer.is_running():
                started = time.monotonic()
                if controller is not None:
                    if managed:
                        if data.time < previous_time:
                            controller.reset(model, data, context)
                            mujoco.mj_forward(model, data)
                        controller.step(model, data, context)
                    else:
                        controller.update(data)
                mujoco.mj_step(model, data)
                previous_time = float(data.time)
                viewer.sync()
                time.sleep(max(0, model.opt.timestep - (time.monotonic() - started)))
    finally:
        if managed:
            controller.close()
