"""Load robot assets in place and add connected track geometry."""

import math
from pathlib import Path
import time

from ..scenarios import Scenario
from .walls import WALL_HEIGHT, WALL_THICKNESS, wall_segments


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


def build_model(robot_path, scenario: Scenario):
    import mujoco

    path = Path(robot_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Robot XML does not exist: {path}")
    # Loading from the original location preserves relative includes and assets.
    spec = mujoco.MjSpec.from_file(str(path))
    # Use pristine geom defaults rather than inheriting robot materials/contact settings.
    clean_spec = mujoco.MjSpec()
    track_default = spec.add_default("line_tracker_environment", spec.default)
    track_default.geom = clean_spec.default.geom
    points = scenario.points()
    terrain = None
    if scenario.terrain.mode != "flat":
        from .terrain import HeightField
        terrain = HeightField(scenario)
        terrain.add_to_spec(spec, track_default)
    else:
        # Ground meets the underside of the track without duplicate road contacts.
        spec.worldbody.add_geom(
            track_default, name="environment_ground", type=mujoco.mjtGeom.mjGEOM_PLANE,
            pos=[0, 0, -0.05], size=[0, 0, 0.1], rgba=[0.57, 0.65, 0.68, 1],
            contype=1, conaffinity=1,
        )
    spec.visual.headlight.active = 1
    spec.visual.headlight.ambient = [0.2, 0.2, 0.2] if terrain else [0.4, 0.4, 0.4]
    spec.visual.headlight.diffuse = [0.3, 0.3, 0.3] if terrain else [0.7, 0.7, 0.7]
    spec.visual.headlight.specular = [0.1, 0.1, 0.1]
    if not any(texture.type == mujoco.mjtTexture.mjTEXTURE_SKYBOX for texture in spec.textures):
        spec.add_texture(
            name="environment_sky", type=mujoco.mjtTexture.mjTEXTURE_SKYBOX,
            builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,
            rgb1=[0.65, 0.77, 0.88], rgb2=[0.92, 0.95, 0.98], width=256, height=1536,
        )
    if terrain is None:
        for index, (start, end) in enumerate(zip(points, points[1:])):
            dx, dy = end[0] - start[0], end[1] - start[1]
            angle = math.atan2(dy, dx)
            for label, width, z, thickness, color, contact in (
                ("floor", scenario.width, -0.025, 0.025, [0.9, 0.9, 0.9, 1], 1),
                ("line", scenario.line_width, 0.0005, 0.0005, [0.015, 0.015, 0.015, 1], 0),
            ):
                spec.worldbody.add_geom(
                    track_default, name=f"track_{label}_{index}",
                    type=mujoco.mjtGeom.mjGEOM_BOX,
                    pos=[(start[0] + end[0]) / 2, (start[1] + end[1]) / 2, z],
                    size=[math.hypot(dx, dy) / 2, width / 2, thickness],
                    quat=[math.cos(angle / 2), 0, 0, math.sin(angle / 2)],
                    rgba=color, contype=contact, conaffinity=contact,
                )
        # Round joins fill the outer corner between rotated rectangles.
        for index, (x, y) in enumerate(points[:-1] if scenario.closed else points):
            for label, radius, z, thickness, color, contact in (
                ("floor", scenario.width / 2, -0.025, 0.025, [0.9, 0.9, 0.9, 1], 1),
                ("line", scenario.line_width / 2, 0.0005, 0.0005, [0.015, 0.015, 0.015, 1], 0),
            ):
                spec.worldbody.add_geom(
                    track_default, name=f"track_{label}_join_{index}",
                    type=mujoco.mjtGeom.mjGEOM_CYLINDER, pos=[x, y, z],
                    size=[radius, thickness, 0], rgba=color,
                    contype=contact, conaffinity=contact,
                )
        if scenario.closed:
            spec.worldbody.add_geom(
                track_default, name="track_start_line", type=mujoco.mjtGeom.mjGEOM_BOX,
                pos=[0, 0, 0.002], size=[0.015, scenario.width / 2, 0.001],
                rgba=[0.1, 0.5, 0.35, 1], contype=0, conaffinity=0,
            )
    for index, (start, end) in enumerate(wall_segments(scenario)):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        angle = math.atan2(dy, dx)
        panels = max(1, math.ceil(length / 0.15)) if terrain else 1
        for panel in range(panels):
            t = (panel + 0.5) / panels
            x, y = start[0] + t*dx, start[1] + t*dy
            bottom = terrain.height(x, y) - scenario.terrain.height - 0.01 if terrain else 0
            top = (terrain.height(x, y) if terrain else 0) + WALL_HEIGHT
            spec.worldbody.add_geom(
                track_default, name=f"corridor_wall_{index}_{panel}", type=mujoco.mjtGeom.mjGEOM_BOX,
                pos=[x, y, (bottom + top)/2],
                size=[length / panels / 2 + 0.002, WALL_THICKNESS / 2, (top-bottom)/2],
                quat=[math.cos(angle / 2), 0, 0, math.sin(angle / 2)],
                rgba=[0.76, 0.81, 0.83, 1], contype=1, conaffinity=1,
            )
    xs, ys = zip(*points)
    spec.worldbody.add_light(
        pos=[(min(xs) + max(xs)) / 2 - (3 if terrain else 0),
             (min(ys) + max(ys)) / 2 - (1.5 if terrain else 0), 5],
        # Oblique illumination reveals slopes without saturating the white road.
        dir=[0.6, 0.3, -1] if terrain else [0, 0, -1],
        diffuse=[0.55, 0.55, 0.55] if terrain else [0.6, 0.6, 0.6],
        ambient=[0, 0, 0] if terrain else [0.15, 0.15, 0.15],
    )
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
