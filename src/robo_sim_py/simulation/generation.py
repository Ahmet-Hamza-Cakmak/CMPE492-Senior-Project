"""Ordered environment generation shared by CLI exports and live simulations.

Stages mutate a shared build context. Later stages can inspect terrain elevation
and scenario geometry without duplicating earlier generation. No viewer is used.
"""

from dataclasses import dataclass
import math
from typing import Any, Protocol

from ..scenarios import Scenario, LoopScenario
from .walls import WALL_HEIGHT, WALL_THICKNESS, wall_segments


@dataclass
class GenerationContext:
    spec: Any
    scenario: Scenario | LoopScenario
    default: Any
    terrain: Any = None

    def height(self, x, y):
        return self.terrain.height(x, y) if self.terrain is not None else 0.0


class GenerationStage(Protocol):
    """A stage adds its geometry to the spec and may enrich shared context."""

    def __call__(self, context: GenerationContext) -> None: ...


def ground_stage(context):
    """Create the physical ground and existing road markings first."""
    import mujoco

    spec, scenario, track_default = context.spec, context.scenario, context.default
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
    context.terrain = terrain


def walls_stage(context):
    """Place existing corridor/loop walls using the generated ground elevation."""
    import mujoco

    spec, scenario, track_default = context.spec, context.scenario, context.default
    terrain = context.terrain
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


def lighting_stage(context):
    import mujoco

    spec, scenario = context.spec, context.scenario
    terrain = context.terrain
    points = scenario.points()
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
    xs, ys = zip(*points)
    spec.worldbody.add_light(
        pos=[(min(xs) + max(xs)) / 2 - (3 if terrain else 0),
             (min(ys) + max(ys)) / 2 - (1.5 if terrain else 0), 5],
        # Oblique illumination reveals slopes without saturating the white road.
        dir=[0.6, 0.3, -1] if terrain else [0, 0, -1],
        diffuse=[0.55, 0.55, 0.55] if terrain else [0.6, 0.6, 0.6],
        ambient=[0, 0, 0] if terrain else [0.15, 0.15, 0.15],
    )


@dataclass(frozen=True)
class GenerationPipeline:
    """Ordered stages; append future obstacle stages after ground and walls."""

    stages: tuple[GenerationStage, ...] = (ground_stage, walls_stage, lighting_stage)

    def build(self, spec, scenario):
        import mujoco

        if spec.find_default("line_tracker_environment") is not None:
            raise ValueError(
                "This XML already defines a generated environment and cannot be used "
                "as a robot model. In the GUI, select 'Import MuJoCo scene XML' "
                "in the top source selector, then choose this file. "
                "In the CLI, use: run --scene PATH_TO_XML."
            )
        clean_spec = mujoco.MjSpec()
        default = spec.add_default("line_tracker_environment", spec.default)
        default.geom = clean_spec.default.geom
        context = GenerationContext(spec, scenario, default)
        for stage in self.stages:
            stage(context)
        return context


def generate_spec(scenario, *, pipeline=None):
    """Generate an environment without a robot, compilation, or viewer."""
    import mujoco

    spec = mujoco.MjSpec()
    (pipeline or GenerationPipeline()).build(spec, scenario)
    return spec


def _texture_png(texture):
    """Encode generated RGB pixels without introducing an image dependency."""
    import struct
    import zlib

    def chunk(kind, data):
        return (struct.pack("!I", len(data)) + kind + data
                + struct.pack("!I", zlib.crc32(kind + data) & 0xffffffff))

    width, height = texture.width, texture.height
    pixels = bytes(texture.data)
    stride = width * 3
    rows = b"".join(b"\x00" + pixels[i:i + stride]
                    for i in range(0, len(pixels), stride))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def export_scene(scenario, destination, *, pipeline=None):
    """Write a reloadable scene and, for terrain, a sibling texture directory.

    Outputs are exclusive: never replace existing XML or asset directories.
    Keep the XML and its sibling assets together when moving an export.
    """
    from pathlib import Path
    import shutil
    import tempfile
    from xml.sax.saxutils import escape

    path = Path(destination).expanduser().absolute()
    asset_path = path.with_name(path.stem + "_assets")
    if path.exists():
        raise FileExistsError(f"Scene already exists: {path}")
    spec = generate_spec(scenario, pipeline=pipeline)
    textures = [texture for texture in spec.textures if texture.data]
    if textures and asset_path.exists():
        raise FileExistsError(f"Scene assets already exist: {asset_path}")
    created_assets = False
    try:
        # Serialize using temporary files, so compilation validates every asset
        # before publishing the XML. The final document uses relative paths.
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory)
            for texture in textures:
                filename = texture.name + ".png"
                (staging / filename).write_bytes(_texture_png(texture))
                texture.data = b""
                texture.file = str(staging / filename)
            spec.compile()
            xml = spec.to_xml()
            for texture in textures:
                filename = texture.name + ".png"
                xml = xml.replace(str(staging / filename),
                                  escape((Path(asset_path.name) / filename).as_posix(), {'"': "&quot;"}))
            if textures:
                asset_path.mkdir()
                created_assets = True
                for source in staging.iterdir():
                    shutil.copyfile(source, asset_path / source.name)
            with path.open("x", encoding="utf-8") as file:
                file.write(xml)
    except BaseException:
        if created_assets:
            shutil.rmtree(asset_path)
        raise
    return path
