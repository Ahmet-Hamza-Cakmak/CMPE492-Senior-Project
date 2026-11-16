"""Initial-pose collision footprints and shared robot-aware scenario preparation."""
from dataclasses import dataclass, replace
from itertools import product
import math
from pathlib import Path


@dataclass(frozen=True)
class RobotFootprint:
    """Conservative enclosing circle about the selected body origin, in metres."""
    body: str
    raw_radius: float
    margin: float
    radius: float
    geometry_count: int


def _nonnegative(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f'{label} must be finite and nonnegative.')


def estimate_robot_footprint(robot_path, *, margin=.05, body=None):
    """Use collision AABBs at qpos0, without stepping physics or loading controllers.

    Includes all descendant collision geometry, including arms at the XML pose.
    World geometry and purely visual geoms are excluded. Multiple robot trees
    require a body name. Dynamics and articulation over time are not assessed.
    """
    _nonnegative(margin, 'Footprint margin')
    import mujoco
    import numpy as np
    path = Path(robot_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f'Robot XML does not exist: {path}')
    try:
        model = mujoco.MjModel.from_xml_path(str(path))
        data = mujoco.MjData(model)
        mujoco.mj_kinematics(model, data)
    except Exception as exc:
        raise ValueError(f'Cannot inspect robot collision geometry: {exc}') from exc
    paired = set(map(int, model.pair_geom1)) | set(map(int, model.pair_geom2))
    collidable = [g for g in range(model.ngeom) if model.geom_bodyid[g] != 0 and
                  (model.geom_contype[g] or model.geom_conaffinity[g] or g in paired)]
    if body:
        root = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body)
        if root <= 0:
            raise ValueError(f'Unknown robot body: {body}; select a non-world body.')
    else:
        roots = {int(model.body_rootid[model.jnt_bodyid[j]]) for j in range(model.njnt)}
        if not roots:
            roots = {int(model.body_rootid[model.geom_bodyid[g]]) for g in collidable}
        if len(roots) != 1:
            raise ValueError('Cannot identify a single robot tree; select --robot-body / a robot body in the GUI, or set a manual robot radius.')
        root = roots.pop()
    def belongs(b):
        while b and b != root:
            b = int(model.body_parentid[b])
        return b == root
    geoms = [g for g in collidable if belongs(int(model.geom_bodyid[g]))]
    if not geoms:
        raise ValueError('Selected robot has no collision geometry; set a manual robot radius.')
    radius = 0.
    signs = np.array(list(product((-1., 1.), repeat=3)))
    for g in geoms:
        if model.geom_type[g] in (mujoco.mjtGeom.mjGEOM_PLANE, mujoco.mjtGeom.mjGEOM_HFIELD):
            raise ValueError('Robot contains plane/heightfield collision geometry; set a manual robot radius or select another body.')
        bounds = model.geom_aabb[g]
        corners = bounds[:3] + signs*bounds[3:]
        world = corners @ data.geom_xmat[g].reshape(3, 3).T + data.geom_xpos[g]
        radius = max(radius, float(np.linalg.norm(world[:, :2]-data.xpos[root, :2], axis=1).max()))
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError('Cannot infer a finite positive robot footprint; set a manual robot radius.')
    return RobotFootprint(mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, root) or str(root),
                          radius, float(margin), radius+margin, len(geoms))


def prepare_scenario(scenario, *, robot_path=None, robot_radius=None, margin=.05, body=None):
    """Resolve footprint, check planar mission connectivity, and freeze population.

    A manual radius is the final radius (margin is only added to inferred sizes).
    Without a robot or override, preserve the scenario's stored/default radius.
    Existing concrete placements are validated, never silently resampled.
    Returns (scenario, inferred footprint or None).
    """
    from .scenarios.population import populate_scenario, navigation_connected
    _nonnegative(margin, 'Footprint margin')
    footprint = None
    if robot_radius is not None:
        _nonnegative(robot_radius, 'Robot radius')
        if robot_radius == 0:
            raise ValueError('Robot radius must be positive.')
        radius = robot_radius
    elif robot_path is not None:
        footprint = estimate_robot_footprint(robot_path, margin=margin, body=body)
        radius = footprint.radius
    else:
        if body:
            raise ValueError('Robot body selection requires a robot model.')
        radius = scenario.objects.robot_radius
    # Check the empty floor before constructing the candidate, so a saved case
    # that no longer fits produces an actionable error without losing placements.
    settings = replace(scenario.objects, robot_radius=float(radius))
    empty = replace(scenario, objects=settings, static_objects=None)
    if not navigation_connected(empty, ()):
        raise ValueError(f'No connected mission path for robot radius {radius:.3f} m. Enlarge passages or select an appropriate manual footprint.')
    candidate = replace(scenario, objects=settings)
    result = populate_scenario(candidate)
    from .scenarios.population import static_objects
    if not navigation_connected(result, static_objects(result)):
        raise ValueError(f'Obstacles block the mission path for robot radius {radius:.3f} m. Adjust geometry/placement settings or regenerate the scenario.')
    return result, footprint
