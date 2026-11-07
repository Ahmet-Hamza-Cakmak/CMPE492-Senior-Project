"""Seeded grid mazes with a shared geometric representation for scene builders."""

from collections import deque
from dataclasses import dataclass
from functools import lru_cache
import math
import random

from shapely.geometry import LineString, box
from shapely.ops import unary_union

from . import Terrain
from .dungeon import DungeonLayout, Room
from .objects import StaticObjectSettings, StaticBox, validate_population

ALGORITHMS = {'dfs': 'Randomized DFS', 'prim': 'Randomized Prim', 'growing-tree': 'Growing Tree'}


@dataclass(frozen=True)
class MazeScenario:
    rows: int = 8
    columns: int = 8
    cell_size: float = 3.0
    width: float = 2.0
    algorithm: str = 'dfs'
    newest_probability: float = .5
    loop_fraction: float = 0.0
    layout_seed: int = 42
    line_width: float = .025
    terrain: Terrain = Terrain()
    objects: StaticObjectSettings = StaticObjectSettings()
    static_objects: tuple[StaticBox, ...] | None = None

    def __post_init__(self):
        for name in ('rows', 'columns'):
            if type(getattr(self, name)) is not int or not 2 <= getattr(self, name) <= 40:
                raise ValueError('Maze rows and columns must be integers from 2 to 40.')
        for name in ('cell_size', 'width', 'line_width', 'newest_probability', 'loop_fraction'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'Maze {name} must be a finite number.')
        if not 0 < self.line_width < self.width or self.cell_size < self.width + .1 - 1e-9:
            raise ValueError('Require 0 < line width < passage width and cell size >= passage width + 0.1 m.')
        if max(self.rows, self.columns)*self.cell_size > 200:
            raise ValueError('Maze ground must not exceed 200 m per side.')
        if self.algorithm not in ALGORITHMS:
            raise ValueError('Maze algorithm must be dfs, prim, or growing-tree.')
        if not 0 <= self.newest_probability <= 1 or not 0 <= self.loop_fraction <= 1:
            raise ValueError('Maze newest probability and loop fraction must be between 0 and 1.')
        if type(self.layout_seed) is not int or not 0 <= self.layout_seed <= 2147483647:
            raise ValueError('Maze layout seed must be an integer from 0 to 2147483647.')
        if not isinstance(self.terrain, Terrain) or self.terrain.mode != 'flat':
            raise ValueError('Mazes currently support flat ground only.')
        validate_population(self)

    @property
    def closed(self):
        return False

    def points(self):
        return list(maze_layout(self).route)

    @property
    def total_length(self):
        return sum(math.dist(a, b) for a, b in zip(self.points(), self.points()[1:]))


@lru_cache(maxsize=32)
def maze_layout(scenario):
    rng = random.Random(scenario.layout_seed)
    rows, cols = scenario.rows, scenario.columns
    def neighbors(cell):
        y, x = divmod(cell, cols)
        return [ny*cols+nx for ny, nx in ((y,x+1),(y+1,x),(y,x-1),(y-1,x))
                if 0 <= ny < rows and 0 <= nx < cols]
    visited = {0}
    edges = []
    if scenario.algorithm == 'prim':
        # Random frontier EDGES, not independently weighted minimum spanning trees.
        frontier = [(0, n) for n in neighbors(0)]
        while frontier:
            i = rng.randrange(len(frontier))
            frontier[i], frontier[-1] = frontier[-1], frontier[i]
            a, b = frontier.pop()
            if b in visited:
                continue
            visited.add(b); edges.append((a,b))
            frontier.extend((b,n) for n in neighbors(b) if n not in visited)
    else:
        active = [0]
        while active:
            if scenario.algorithm == 'dfs' or scenario.newest_probability == 1:
                i = len(active)-1
            elif scenario.newest_probability == 0:
                i = rng.randrange(len(active))
            else:
                i = len(active)-1 if rng.random() < scenario.newest_probability else rng.randrange(len(active))
            a = active[i]
            options = [n for n in neighbors(a) if n not in visited]
            if not options:
                active.pop(i)
                continue
            b = rng.choice(options)
            visited.add(b); edges.append((a,b)); active.append(b)
    carved = {tuple(sorted(edge)) for edge in edges}
    remaining = [(a,b) for a in range(rows*cols) for b in neighbors(a)
                 if a < b and (a,b) not in carved]
    rng.shuffle(remaining)
    edges.extend(remaining[:math.floor(scenario.loop_fraction*len(remaining))])
    centers = [(x*scenario.cell_size, y*scenario.cell_size) for y in range(rows) for x in range(cols)]
    adjacency = [[] for _ in centers]
    for a,b in edges:
        adjacency[a].append(b); adjacency[b].append(a)
    parents = {0: None}
    queue = deque([0]); goal = 0
    while queue:
        goal = queue.popleft()
        for b in adjacency[goal]:
            if b not in parents:
                parents[b] = goal; queue.append(b)
    route = []; node = goal
    while node is not None:
        route.append(centers[node]); node = parents[node]
    rooms = tuple(Room(x,y,scenario.width,scenario.width,'rectangular') for x,y in centers)
    passages = tuple((centers[a],centers[b]) for a,b in edges)
    floor = unary_union([r.polygon() for r in rooms] + [LineString(p).buffer(scenario.width/2, cap_style='square', join_style='mitre') for p in passages])
    if floor.geom_type != 'Polygon' or not floor.is_valid:
        raise ValueError('Generated maze floor is not a valid connected polygon.')
    half = scenario.cell_size/2
    bounds = (-half,-half,(cols-.5)*scenario.cell_size,(rows-.5)*scenario.cell_size)
    if not box(*bounds).covers(floor):
        raise ValueError('Maze exceeds ground bounds.')
    return DungeonLayout(rooms,passages,tuple(edges),floor,tuple(reversed(route)),bounds)
