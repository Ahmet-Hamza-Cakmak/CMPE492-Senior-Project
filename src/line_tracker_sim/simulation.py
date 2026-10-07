"""Load robot assets in place and add connected track geometry."""

import math
from pathlib import Path
import time

from .scenario import Scenario


def example_robot():
    return Path(__file__).parent / "assets" / "robot.xml"


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
    # Ground meets the underside of the track without duplicate road contacts.
    spec.worldbody.add_geom(
        track_default, name="environment_ground", type=mujoco.mjtGeom.mjGEOM_PLANE,
        pos=[0, 0, -0.05], size=[0, 0, 0.1], rgba=[0.57, 0.65, 0.68, 1],
        contype=1, conaffinity=1,
    )
    spec.visual.headlight.active = 1
    spec.visual.headlight.ambient = [0.4, 0.4, 0.4]
    spec.visual.headlight.diffuse = [0.7, 0.7, 0.7]
    spec.visual.headlight.specular = [0.1, 0.1, 0.1]
    if not any(texture.type == mujoco.mjtTexture.mjTEXTURE_SKYBOX for texture in spec.textures):
        spec.add_texture(
            name="environment_sky", type=mujoco.mjtTexture.mjTEXTURE_SKYBOX,
            builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,
            rgb1=[0.65, 0.77, 0.88], rgb2=[0.92, 0.95, 0.98], width=256, height=1536,
        )
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
    for index, (x, y) in enumerate(points):
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
    xs, ys = zip(*points)
    spec.worldbody.add_light(
        pos=[(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 5],
        dir=[0, 0, -1], diffuse=[0.6, 0.6, 0.6], ambient=[0.15, 0.15, 0.15],
    )
    return spec.compile()


def run(model, scenario, *, auto_follow=False):
    import mujoco
    import mujoco.viewer

    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    from .controller import LineFollower
    controller = LineFollower(model, scenario) if auto_follow else None
    points = scenario.points()
    xs, ys = zip(*points)
    with mujoco.viewer.launch_passive(model, data) as viewer:
        viewer.cam.lookat[:] = [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 0]
        viewer.cam.distance = max(max(xs) - min(xs), max(ys) - min(ys), scenario.width) * 1.6 + 1
        viewer.cam.elevation = -65
        while viewer.is_running():
            started = time.monotonic()
            if controller is not None:
                controller.update(data)
            mujoco.mj_step(model, data)
            viewer.sync()
            time.sleep(max(0, model.opt.timestep - (time.monotonic() - started)))
