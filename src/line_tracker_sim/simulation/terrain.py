"""Repeatable physical height fields with road markings painted on the surface."""

import math

import numpy as np


class HeightField:
    def __init__(self, scenario):
        self.scenario = scenario
        points = np.asarray(scenario.points())
        margin = scenario.width / 2 + 0.6
        self.low = points.min(axis=0) - margin
        self.high = points.max(axis=0) + margin
        span = self.high - self.low
        settings = scenario.terrain
        counts = np.maximum(2, np.ceil(span / max(span) * (settings.resolution - 1)).astype(int) + 1)
        self.nx, self.ny = map(int, counts)
        if max(span / (counts - 1)) > settings.spacing / 6:
            raise ValueError("Terrain grid is too coarse for this track. Increase grid resolution or bump spacing.")
        x, y = np.meshgrid(np.linspace(self.low[0], self.high[0], self.nx),
                           np.linspace(self.low[1], self.high[1], self.ny))
        scale = 2 * math.pi / settings.spacing
        if settings.mode == "waves":
            heights = np.sin(x * scale) * np.cos(y * scale)
        else:
            rng = np.random.default_rng(settings.seed)
            heights = np.zeros_like(x)
            for _ in range(8):
                angle, phase = rng.uniform(0, 2 * math.pi, 2)
                frequency = scale * rng.uniform(0.5, 1)
                heights += np.sin(frequency * (x * np.cos(angle) + y * np.sin(angle)) + phase)
        heights -= heights.min()
        # A level starting patch accommodates both bundled robot footprints.
        blend = np.clip((np.hypot(x, y) - 0.45) / 0.4, 0, 1)
        heights *= blend * blend * (3 - 2 * blend)
        peak = heights.max()
        self.normalized = heights / peak if peak else heights
        self.heights = self.normalized * settings.height

    def height(self, x, y):
        """Bilinear elevation for placing walls; collision uses MuJoCo's triangles."""
        u, v = np.clip((np.asarray([x, y]) - self.low) / (self.high - self.low), 0, 1)
        u, v = u * (self.nx - 1), v * (self.ny - 1)
        i, j = min(int(u), self.nx - 2), min(int(v), self.ny - 2)
        a, b = u - i, v - j
        h = self.heights
        return float((1-b)*((1-a)*h[j, i]+a*h[j, i+1]) + b*((1-a)*h[j+1, i]+a*h[j+1, i+1]))

    def add_to_spec(self, spec, default):
        import mujoco

        span = self.high - self.low
        # MuJoCo image rows run from high Y to low Y on a height field.
        count = min(2048, max(256, math.ceil(max(span) / (self.scenario.line_width / 2))))
        nx, ny = np.maximum(2, np.ceil(span / max(span) * count).astype(int))
        x, y = np.meshgrid(np.linspace(*[self.low[0], self.high[0]], nx),
                           np.linspace(*[self.low[1], self.high[1]], ny))
        distance = np.full_like(x, np.inf)
        points = self.scenario.points()
        for a, b in zip(points, points[1:]):
            dx, dy = b[0]-a[0], b[1]-a[1]
            t = np.clip(((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy), 0, 1)
            distance = np.minimum(distance, np.hypot(x-a[0]-t*dx, y-a[1]-t*dy))
        pixels = np.empty((*x.shape, 3), dtype=np.uint8)
        pixels[:] = [145, 166, 173]
        pixels[distance <= self.scenario.width / 2] = [230, 230, 230]
        pixels[distance <= max(self.scenario.line_width / 2, max(span)/count/2)] = [4, 4, 4]
        if self.scenario.closed:
            pixels[(abs(x) <= 0.015) & (abs(y) <= self.scenario.width/2)] = [26, 128, 89]
        spec.add_texture(name="terrain_markings", type=mujoco.mjtTexture.mjTEXTURE_2D,
                         width=int(nx), height=int(ny), nchannel=3, data=pixels[::-1].copy().ravel())
        textures = [""] * int(mujoco.mjtTextureRole.mjNTEXROLE)
        textures[int(mujoco.mjtTextureRole.mjTEXROLE_RGB)] = "terrain_markings"
        spec.add_material(name="terrain_material", textures=textures, texrepeat=[1, 1],
                          texuniform=False, rgba=[1, 1, 1, 1])
        height = self.scenario.terrain.height
        spec.add_hfield(name="terrain_surface", nrow=self.ny, ncol=self.nx,
                        size=[span[0]/2, span[1]/2, max(height, 1e-6), 0.1],
                        userdata=(self.normalized if height else self.normalized * 0).ravel())
        spec.worldbody.add_geom(default, name="environment_ground", type=mujoco.mjtGeom.mjGEOM_HFIELD,
                                hfieldname="terrain_surface", material="terrain_material",
                                pos=[*(self.low + self.high)/2, 0], contype=1, conaffinity=1)
