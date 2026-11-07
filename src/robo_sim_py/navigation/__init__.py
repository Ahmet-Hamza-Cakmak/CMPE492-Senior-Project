"""Global planning against known, static generated geometry (ideal map knowledge)."""

from dataclasses import dataclass
import heapq
import math

from shapely.geometry import Point, LineString
from shapely.ops import unary_union
from shapely.prepared import prep


@dataclass(frozen=True)
class PlannedRoute:
    points: tuple
    length: float
    expanded_nodes: int
    resolution: float


def astar(floor, obstacles, start, goal, *, resolution=.25, clearance=.3, max_nodes=500_000):
    """Eight-neighbor A*, validating complete edges to prevent corner cutting.

    The circular clearance model includes robot footprint plus tracking margin.
    Geometry is queried lazily, avoiding allocation of an entire 200 m grid.
    """
    for value, name in ((resolution, 'Grid resolution'), (clearance, 'Navigation clearance')):
        if isinstance(value,bool) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'{name} must be finite and positive.')
    if type(max_nodes) is not int or max_nodes <= 0:
        raise ValueError('Planner node budget must be a positive integer.')
    start, goal = tuple(start), tuple(goal)
    if len(start)!=2 or len(goal)!=2 or not all(math.isfinite(v) for v in (*start,*goal)):
        raise ValueError('Planner endpoints must be finite XY coordinates.')
    free = floor.buffer(-clearance)
    obstacles = tuple(obstacles)
    if obstacles:
        free = free.difference(unary_union(obstacles).buffer(clearance))
    parts=list(free.geoms) if free.geom_type=='MultiPolygon' else [free]
    free=next((part for part in parts if part.covers(Point(start)) and part.covers(Point(goal))),None)
    if free is None:
        raise ValueError('No start-to-goal path at this navigation clearance; reduce clearance or change the environment.')
    if math.dist(start,goal)<1e-9:
        raise ValueError('Start and goal must be distinct.')
    prepared=prep(free)
    def visible(a,b):
        return prepared.covers(LineString((a,b)))
    if visible(start,goal):
        return PlannedRoute((start,goal),math.dist(start,goal),0,resolution)
    xmin,ymin,xmax,ymax=free.bounds
    def position(node):
        return start[0]+node[0]*resolution,start[1]+node[1]*resolution
    def heuristic(node):
        return math.dist(position(node),goal)
    parents={}; costs={(0,0):0.};closed=set();valid={}
    queue=[(heuristic((0,0)),0.,(0,0))]
    directions=((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1))
    while queue:
        _,cost,node=heapq.heappop(queue)
        if node in closed:
            continue
        closed.add(node)
        if len(closed)>max_nodes:
            raise ValueError('A* exceeded its node budget; increase grid spacing or reduce map size.')
        current=position(node)
        if math.dist(current,goal)<=2*resolution and visible(current,goal):
            chain=[node]
            while chain[-1] in parents:
                chain.append(parents[chain[-1]])
            raw=[position(n) for n in reversed(chain)]
            if raw[-1]!=goal:
                raw.append(goal)
            # Retain the farthest visible waypoint; every shortcut is checked
            # against inflated geometry, not merely its endpoints.
            path=[raw[0]];i=0
            while i<len(raw)-1:
                j=len(raw)-1
                while j>i+1 and not visible(raw[i],raw[j]):
                    j-=1
                path.append(raw[j]);i=j
            return PlannedRoute(tuple(path),sum(math.dist(a,b) for a,b in zip(path,path[1:])),len(closed),resolution)
        for dx,dy in directions:
            neighbor=(node[0]+dx,node[1]+dy)
            if neighbor in closed:
                continue
            point=position(neighbor)
            if neighbor not in valid:
                valid[neighbor]=(xmin<=point[0]<=xmax and ymin<=point[1]<=ymax and prepared.covers(Point(point)))
            if not valid[neighbor] or not visible(current,point):
                continue
            candidate=cost+resolution*math.hypot(dx,dy)
            if candidate<costs.get(neighbor,math.inf):
                costs[neighbor]=candidate;parents[neighbor]=node
                heapq.heappush(queue,(candidate+heuristic(neighbor),candidate,neighbor))
    raise ValueError('A* found no grid path. A geometric path may exist; try a finer --grid-resolution.')


def plan_scenario(scenario, *, resolution=.25, clearance=None):
    """Known-map planning; loops visit protected quarter-lap anchors in order."""
    from ..scenarios import Scenario, LoopScenario, DungeonScenario, MazeScenario
    from ..scenarios.spatial import placement_geometry
    from ..scenarios.population import static_objects
    if not isinstance(scenario,(Scenario,LoopScenario,DungeonScenario,MazeScenario)) or scenario.terrain.mode != 'flat':
        raise ValueError('A* navigation requires a generated flat scenario; uneven terrain needs its own controller.')
    geometry=placement_geometry(scenario)
    radius=max(.3,scenario.objects.robot_radius) if clearance is None else clearance
    if radius<.25:
        raise ValueError('Simple-robot navigation clearance must be at least 0.25 m (footprint plus tracking margin).')
    obstacles=tuple(obj.footprint() for obj in static_objects(scenario))
    anchors=geometry.anchors + (geometry.anchors[0],) if scenario.closed else geometry.anchors
    points=[]; expanded=0; actual_resolution=resolution
    for start,goal in zip(anchors,anchors[1:]):
        # A geometrically connected gap can fall between coarse grid samples.
        for refinement in range(5):
            try:
                part=astar(geometry.floor,obstacles,start,goal,
                           resolution=resolution/(2**refinement),clearance=radius)
                break
            except ValueError as exc:
                if 'no grid path' not in str(exc) or refinement == 4:
                    raise
        points.extend(part.points if not points else part.points[1:])
        expanded+=part.expanded_nodes
        actual_resolution=min(actual_resolution,part.resolution)
    return PlannedRoute(tuple(points),sum(math.dist(a,b) for a,b in zip(points,points[1:])),expanded,actual_resolution)


def plan_dungeon(scenario, *, resolution=.25, clearance=None):
    """Compatibility entry point for room and maze navigation."""
    from ..scenarios import DungeonScenario, MazeScenario
    if not isinstance(scenario,(DungeonScenario,MazeScenario)):
        raise ValueError('Dungeon navigation requires a generated dungeon or maze.')
    return plan_scenario(scenario,resolution=resolution,clearance=clearance)



def draw_route(scene, route):
    """Blue viewer-only segments; never add collision geometry to the model."""
    import mujoco
    import numpy as np

    scene.ngeom = 0
    for a,b in zip(route.points,route.points[1:]):
        if scene.ngeom >= scene.maxgeom:
            break
        geom = scene.geoms[scene.ngeom]
        mujoco.mjv_initGeom(geom,mujoco.mjtGeom.mjGEOM_LINE,np.zeros(3),np.zeros(3),
                            np.eye(3).ravel(),np.array([.05,.35,.95,1.]))
        mujoco.mjv_connector(geom,mujoco.mjtGeom.mjGEOM_LINE,3.,[a[0],a[1],.025],[b[0],b[1],.025])
        scene.ngeom += 1
