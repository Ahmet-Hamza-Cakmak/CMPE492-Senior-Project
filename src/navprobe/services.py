"""UI-independent application services for all supported scenario workflows.

No argparse namespaces, terminal output, viewers, or process exits are used here.
"""
from dataclasses import dataclass, field, fields, replace
import json
from pathlib import Path
from typing import Any

from .scenarios import CIRCUITS, Corridor, LoopScenario, Scenario, DungeonScenario, MazeScenario
from .scenarios.library import (BUNDLED_DIRECTORY, ScenarioPreset, discover_presets,
                               load_preset, save_preset, user_scenario_directory)


@dataclass(frozen=True)
class ScenarioOptions:
    """Scenario sources and overrides. None retains the selected source value.

    Field names match CLI flags with hyphens replaced by underscores. ``scenario``
    accepts JSON paths, existing scenario objects, or ScenarioPreset instances.
    """
    scenario: Any = None
    preset: str | None = None
    scenic: str | Path | None = None
    scenic_seed: int | None = None
    maze: bool = False
    dungeon: bool = False
    loop: str | None = None
    corridor: tuple | None = None
    maze_algorithm: str | None = None
    maze_rows: int | None = None
    maze_columns: int | None = None
    cell_size: float | None = None
    newest_probability: float | None = None
    loop_fraction: float | None = None
    map_width: float | None = None
    map_height: float | None = None
    rooms: int | None = None
    room_min: float | None = None
    room_max: float | None = None
    room_shape: str | None = None
    layout_seed: int | None = None
    static_objects: int | None = None
    object_seed: int | None = None
    object_min_size: float | None = None
    object_max_size: float | None = None
    object_height: float | None = None
    object_clearance: float | None = None
    object_placement: str | None = None
    robot_radius: float | None = None
    footprint_margin: float | None = None
    robot_body: str | None = None
    robot: str | Path | None = None
    width: float | None = None
    line_width: float | None = None
    radius: float | None = None
    terrain: str | None = None
    height: float | None = None
    spacing: float | None = None
    resolution: int | None = None
    seed: int | None = None
    library: str | Path | None = None
    name: str | None = None
    description: str | None = None

    @classmethod
    def from_mapping(cls, values):
        """Translate interface fields, ignoring unrelated interface-only keys."""
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in values.items() if k in names})

    def has_generation_settings(self):
        return any(getattr(self, f.name) is not None and getattr(self, f.name) is not False
                   for f in fields(ScenarioOptions) if f.name not in ('library', 'name', 'description'))


@dataclass(frozen=True)
class ScenarioResult:
    preset: ScenarioPreset
    footprint: Any = None
    warnings: tuple[str, ...] = ()

    @property
    def scenario(self):
        return self.preset.scenario


@dataclass(frozen=True)
class PresetEntry:
    path: Path
    preset: ScenarioPreset
    origin: str


@dataclass(frozen=True)
class PresetCatalog:
    entries: tuple[PresetEntry, ...]
    errors: tuple[str, ...]


def list_presets(library=None):
    entries, errors = [], []
    for directory, origin in ((BUNDLED_DIRECTORY, "built-in"),
                              (Path(library or user_scenario_directory()).expanduser(), "saved")):
        found, failures = discover_presets(directory)
        entries.extend(PresetEntry(path, preset, origin) for path, preset in found)
        errors.extend(f"{directory}: {message}" for message in failures)
    return PresetCatalog(tuple(entries), tuple(errors))


def list_robots():
    from .assets import EXAMPLES
    return tuple(EXAMPLES)


def resolve_robot(robot=None):
    key = robot or "simple_robot"
    path = next((entry.path for entry in list_robots() if entry.key == str(key)), Path(key).expanduser()).resolve()
    if not path.is_file():
        raise ValueError(f"Robot does not exist: {path}. Use list_robots() for registered keys.")
    return path


def _scenario_options(options, changes):
    if options is None:
        options = ScenarioOptions()
    elif isinstance(options, (ScenarioPreset, Scenario, LoopScenario, DungeonScenario, MazeScenario)):
        options = ScenarioOptions(scenario=options)
    if not isinstance(options, ScenarioOptions):
        raise TypeError("Expected ScenarioOptions, a scenario, or ScenarioPreset.")
    return replace(options, **changes) if changes else options


def _validate_source(options):
    allowed_scenario = (str, Path, ScenarioPreset, Scenario, LoopScenario, DungeonScenario, MazeScenario)
    if options.scenario is not None and not isinstance(options.scenario, allowed_scenario):
        raise TypeError('scenario must be a JSON path, scenario object, or ScenarioPreset.')
    for key in ('scenario', 'preset', 'scenic', 'loop', 'robot'):
        value = getattr(options, key)
        if isinstance(value, str) and not value.strip():
            raise ValueError(f'{key} must not be empty.')
    for key in ('preset', 'loop'):
        if getattr(options, key) is not None and not isinstance(getattr(options, key), str):
            raise TypeError(f'{key} must be a string.')
    for key in ('scenic', 'robot'):
        if getattr(options, key) is not None and not isinstance(getattr(options, key), (str, Path)):
            raise TypeError(f'{key} must be a path or string.')
    if type(options.maze) is not bool or type(options.dungeon) is not bool:
        raise ValueError('maze and dungeon must be booleans.')
    sources = (options.scenario is not None, options.preset is not None, options.scenic is not None,
               options.maze, options.dungeon, options.loop is not None, options.corridor is not None)
    if sum(bool(value) for value in sources) > 1:
        raise ValueError("Choose only one scenario source: scenario, preset, scenic, maze, dungeon, loop, or corridor.")
    if options.corridor is not None and not options.corridor:
        raise ValueError("corridor must contain at least one (length, turn) pair.")


def configure_scenario(options=None, *, robot_path=None, **changes):
    """Build, edit, validate, and populate a scenario without UI or terminal output."""
    args = _scenario_options(options, changes)
    _validate_source(args)
    inferred = None
    warnings = ()
    if getattr(args, "scenic_seed", None) is not None and not getattr(args, "scenic", None):
        raise ValueError("--scenic-seed requires --scenic.")
    if getattr(args, "scenic", None):
        from .scenarios.scenic_adapter import sample_scenic
        preset = sample_scenic(args.scenic, seed=42 if args.scenic_seed is None else args.scenic_seed)
    elif args.scenario:
        preset = (args.scenario if isinstance(args.scenario, ScenarioPreset) else
                  ScenarioPreset("Custom scenario", "", args.scenario) if isinstance(args.scenario, (Scenario, LoopScenario, DungeonScenario, MazeScenario)) else
                  load_preset(Path(args.scenario).expanduser()))
    elif args.preset:
        catalog = list_presets(args.library)
        warnings = catalog.errors
        matches = [entry.preset for entry in catalog.entries
                   if args.preset in (entry.path.stem, entry.preset.name)]
        if len(matches) != 1:
            raise ValueError("Preset must match exactly one name or file stem; use 'list presets'.")
        preset = matches[0]
    else:
        scenario = (LoopScenario(args.loop) if args.loop else
                    Scenario(tuple(Corridor(*part) for part in args.corridor)) if args.corridor else
                    Scenario((Corridor(2),)))
        preset = ScenarioPreset("Custom track", "", scenario)
    scenario = preset.scenario
    maze_options = {key: getattr(args, option) for key, option in (
        ("rows", "maze_rows"), ("columns", "maze_columns"), ("cell_size", "cell_size"),
        ("algorithm", "maze_algorithm"), ("newest_probability", "newest_probability"),
        ("loop_fraction", "loop_fraction")) if getattr(args, option, None) is not None}
    if args.maze:
        scenario = MazeScenario()
        preset = ScenarioPreset("Custom maze", "", scenario)
    if maze_options and not isinstance(scenario, MazeScenario):
        raise ValueError("Maze settings require --maze or a maze preset/JSON.")
    dungeon_options = {key: getattr(args, option) for key, option in (
        ("map_width", "map_width"), ("map_height", "map_height"), ("room_count", "rooms"),
        ("room_min", "room_min"), ("room_max", "room_max"), ("room_shape", "room_shape"),
        ) if getattr(args, option, None) is not None}
    if args.dungeon:
        scenario = DungeonScenario()
    elif dungeon_options and not isinstance(scenario, DungeonScenario):
        raise ValueError("Dungeon settings require --dungeon or a dungeon preset/JSON.")
    updates = {key: getattr(args, key) for key in ("width", "line_width", "radius") if getattr(args, key) is not None}
    updates.update(dungeon_options)
    updates.update(maze_options)
    if args.layout_seed is not None:
        if not isinstance(scenario, (DungeonScenario, MazeScenario)):
            raise ValueError("--layout-seed requires a dungeon or maze scenario.")
        updates["layout_seed"] = args.layout_seed
    if "radius" in updates and not scenario.closed:
        raise ValueError("--radius requires a loop scenario.")
    terrain = {key: getattr(args, option) for key, option in
               (("mode", "terrain"), ("height", "height"), ("spacing", "spacing"),
                ("resolution", "resolution"), ("seed", "seed")) if getattr(args, option) is not None}
    updates["terrain"] = replace(scenario.terrain, **terrain)
    object_options = {key: getattr(args, option) for key, option in (
        ("count", "static_objects"), ("seed", "object_seed"), ("min_size", "object_min_size"),
        ("max_size", "object_max_size"), ("height", "object_height"), ("clearance", "object_clearance"),
        ("placement", "object_placement"), ("robot_radius", "robot_radius"))
        if getattr(args, option, None) is not None}
    if object_options:
        updates["objects"] = replace(scenario.objects, **object_options)
    def placement_changed(key, value):
        if key == "objects":
            value = replace(value, robot_radius=scenario.objects.robot_radius)
        return value != getattr(scenario, key)
    if any(placement_changed(key, value) for key, value in updates.items()):
        updates["static_objects"] = None
    scenario = replace(scenario, **updates)
    selected_robot = robot_path or getattr(args, "robot", None)
    if selected_robot:
        from .assets import EXAMPLES
        selected_robot = next((example.path for example in EXAMPLES if example.key == str(selected_robot)), selected_robot)
    if selected_robot or args.robot_radius is not None:
        from .footprint import prepare_scenario
        scenario, inferred = prepare_scenario(
            scenario, robot_path=selected_robot, robot_radius=args.robot_radius,
            margin=.05 if args.footprint_margin is None else args.footprint_margin, body=args.robot_body)
    else:
        if args.robot_body or args.footprint_margin is not None:
            raise ValueError("--robot-body/--footprint-margin requires --robot (or run's selected robot).")
        from .footprint import prepare_scenario
        scenario, _ = prepare_scenario(scenario)
    return ScenarioResult(ScenarioPreset(args.name or preset.name,
                          preset.description if args.description is None else args.description, scenario), inferred, warnings)


def create_scenario(options=None, **changes):
    """Return a prepared ScenarioPreset; see ScenarioOptions for all settings."""
    return configure_scenario(options, **changes).preset


def export_scenario(preset, destination):
    """Save scenario JSON explicitly, refusing to overwrite an existing file."""
    if not isinstance(preset, ScenarioPreset):
        preset = ScenarioPreset("Scenario", "", preset)
    path = Path(destination).expanduser()
    payload = preset.to_dict()
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return path


@dataclass(frozen=True)
class GeneratedEnvironment:
    path: Path
    result: ScenarioResult

    @property
    def scenario(self):
        return self.result.scenario


def generate_environment(options=None, destination="scene.xml", **changes):
    """Configure and export an environment without opening a viewer."""
    from .generation import export_scene
    result = configure_scenario(options, **changes)
    return GeneratedEnvironment(export_scene(result.scenario, destination), result)


@dataclass(frozen=True)
class ValidationResult:
    kind: str
    name: str
    path: Path
    mode: str | None = None
    digest: str | None = None


def validate_input(path, *, menagerie=None):
    """Validate JSON/XML/ZIP data without importing a supplied Python controller."""
    path = Path(path).expanduser().resolve()
    if path.suffix.lower() == ".zip":
        from .experiments import open_package
        with open_package(path, menagerie_directory=menagerie) as experiment:
            return ValidationResult("package", experiment.name, path, experiment.mode, experiment.digest)
    if path.suffix.lower() == ".xml":
        from .simulation import load_scene
        load_scene(path)
        return ValidationResult("scene", path.stem, path)
    preset = load_preset(path)
    return ValidationResult("scenario", preset.name, path)
