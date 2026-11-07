"""Seeded BSP rooms and corridors; no Scenic or simulator dependency."""

from dataclasses import dataclass
from functools import lru_cache
import math
import random

from shapely.geometry import Point, LineString, box
from shapely.ops import unary_union

from . import Terrain
from .objects import StaticObjectSettings, StaticBox


@dataclass(frozen=True)
class Room:
    x: float
    y: float
    width: float
    height: float
    shape: str

    def polygon(self):
        if self.shape == 'circular':
            return Point(self.x, self.y).buffer(self.width / 2, quad_segs=24)
        return box(self.x-self.width/2, self.y-self.height/2,
                   self.x+self.width/2, self.y+self.height/2)


@dataclass(frozen=True)
class DungeonLayout:
    rooms: tuple
    passages: tuple
    edges: tuple
    floor: object
    route: tuple
    bounds: tuple


@dataclass(frozen=True)
class DungeonScenario:
    """Room sizes are side lengths or diameters, in metres; width is passage width."""
    map_width: float = 200.0
    map_height: float = 200.0
    room_count: int = 6
    room_min: float = 8.0
    room_max: float = 16.0
    room_shape: str = 'rectangular'
    layout_seed: int = 42
    width: float = 3.0
    line_width: float = 0.025
    terrain: Terrain = Terrain()
    objects: StaticObjectSettings = StaticObjectSettings()
    static_objects: tuple[StaticBox, ...] | None = None

    def __post_init__(self):
        for name in ('map_width', 'map_height', 'room_min', 'room_max', 'width', 'line_width'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be a finite positive number.')
        if max(self.map_width, self.map_height) > 200:
            raise ValueError('Dungeon bounds must not exceed 200 m per side.')
        if type(self.room_count) is not int or not 2 <= self.room_count <= 64:
            raise ValueError('Dungeon room count must be an integer from 2 to 64.')
        if type(self.layout_seed) is not int or not 0 <= self.layout_seed <= 2147483647:
            raise ValueError('Dungeon layout seed must be an integer from 0 to 2147483647.')
        if self.room_shape not in ('rectangular', 'circular'):
            raise ValueError('Dungeon room shape must be rectangular or circular.')
        if not self.line_width < self.width < self.room_min <= self.room_max:
            raise ValueError('Require line width < corridor width < minimum room size <= maximum room size.')
        if self.terrain.mode != 'flat':
            raise ValueError('BSP dungeons currently support flat ground only.')
        if not isinstance(self.objects, StaticObjectSettings):
            raise ValueError('Dungeon objects must be StaticObjectSettings.')
        if self.static_objects is not None and (not isinstance(self.static_objects, tuple) or
                                                not all(isinstance(obj, StaticBox) for obj in self.static_objects)):
            raise ValueError('Concrete static objects must be an immutable tuple.')
        # Eager validation ensures GUI and CLI reject infeasible requests alike.
        dungeon_layout(self)
        if self.static_objects is not None:
            from .dungeon_population import validate_objects
            validate_objects(self, self.static_objects)

    @property
    def closed(self):
        return False

    @property
    def total_length(self):
        return sum(math.dist(a, b) for a, b in zip(self.points(), self.points()[1:]))

    def points(self):
        """A known start-to-goal route for the baseline controller, not exploration."""
        return list(dungeon_layout(self).route)


@lru_cache(maxsize=32)
def dungeon_layout(scenario):
    # Common geometry consumer entry point for room and grid layouts.
    from .maze import MazeScenario, maze_layout
    if isinstance(scenario, MazeScenario):
        return maze_layout(scenario)
    rng = random.Random(scenario.layout_seed)
    margin = 0.3
    minimum = scenario.room_min + 2*margin
    # Tree nodes retain topology; each split links its two connected subtrees.
    leaves = [(0., 0., scenario.map_width, scenario.map_height, ())]
    links = []
    while len(leaves) < scenario.room_count:
        choices = [(i, leaf) for i, leaf in enumerate(leaves)
                   if leaf[2] >= 2*minimum or leaf[3] >= 2*minimum]
        if not choices:
            raise ValueError('Requested room count does not fit BSP bounds/minimum room size; enlarge bounds, reduce rooms or minimum size.')
        i, (x, y, w, h, key) = max(choices, key=lambda entry: entry[1][2]*entry[1][3])
        axes = [axis for axis, span in ((0, w), (1, h)) if span >= 2*minimum]
        axis = rng.choice(axes)
        span = (w, h)[axis]
        cut = rng.uniform(minimum, span-minimum)
        if axis == 0:
            children = [(x,y,cut,h,key+(0,)), (x+cut,y,w-cut,h,key+(1,))]
        else:
            children = [(x,y,w,cut,key+(0,)), (x,y+cut,w,h-cut,key+(1,))]
        leaves[i:i+1] = children
        links.append(key)
    if any(min(w,h) < minimum for x,y,w,h,key in leaves):
        raise ValueError('Ground bounds are too small for the minimum room size.')
    rooms = []
    for x,y,w,h,key in leaves:
        rw = rng.uniform(scenario.room_min, min(scenario.room_max,w-2*margin))
        rh = rng.uniform(scenario.room_min, min(scenario.room_max,h-2*margin))
        if scenario.room_shape == 'circular':
            rw = rh = min(rw,rh)
        cx = rng.uniform(x+margin+rw/2, x+w-margin-rw/2)
        cy = rng.uniform(y+margin+rh/2, y+h-margin-rh/2)
        rooms.append(Room(cx,cy,rw,rh,scenario.room_shape))
    edges, passages = [], []
    for key in reversed(links):
        left = [i for i,leaf in enumerate(leaves) if leaf[4][:len(key)+1] == key+(0,)]
        right = [i for i,leaf in enumerate(leaves) if leaf[4][:len(key)+1] == key+(1,)]
        a,b = min(((a,b) for a in left for b in right),
                  key=lambda pair: math.dist((rooms[pair[0]].x,rooms[pair[0]].y), (rooms[pair[1]].x,rooms[pair[1]].y)))
        p,q = (rooms[a].x,rooms[a].y),(rooms[b].x,rooms[b].y)
        bend = (q[0],p[1]) if rng.randrange(2) else (p[0],q[1])
        path = tuple(v for i,v in enumerate((p,bend,q)) if i == 0 or v != (p,bend,q)[i-1])
        edges.append((a,b));passages.append(path)
    # Normalize spawn to (0,0) for bundled robots, retaining original bounds.
    ox,oy = rooms[0].x,rooms[0].y
    rooms = tuple(Room(r.x-ox,r.y-oy,r.width,r.height,r.shape) for r in rooms)
    passages = tuple(tuple((x-ox,y-oy) for x,y in path) for path in passages)
    floor = unary_union([r.polygon() for r in rooms] +
                        [LineString(path).buffer(scenario.width/2, cap_style='square', join_style='mitre') for path in passages])
    if floor.geom_type != 'Polygon' or not floor.is_valid:
        raise ValueError('Generated dungeon is not a valid connected floor.')
    bounds = (-ox,-oy,scenario.map_width-ox,scenario.map_height-oy)
    if not box(*bounds).covers(floor):
        raise ValueError('Generated dungeon exceeds ground bounds; reduce passage width.')
    # BFS tree selects a distant goal by room-edge distance.
    parents = {0: None};queue = [0]
    adjacency = {i:[] for i in range(len(rooms))}
    for index,(a,b) in enumerate(edges):
        adjacency[a].append((b,index,False));adjacency[b].append((a,index,True))
    for a in queue:
        for b,index,reverse in adjacency[a]:
            if b not in parents:
                parents[b]=(a,index,reverse);queue.append(b)
    if len(parents) != len(rooms):
        raise ValueError('Dungeon room graph is disconnected.')
    steps=[];node=queue[-1]
    while parents[node] is not None:
        previous,index,reverse=parents[node];steps.append(passages[index][::-1] if reverse else passages[index]);node=previous
    route=[(0.,0.)]
    for path in reversed(steps):
        route.extend(p for p in path[1:] if p != route[-1])
    return DungeonLayout(rooms,passages,tuple(edges),floor,tuple(route),bounds)
