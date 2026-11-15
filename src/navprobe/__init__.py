"""NavProbe: randomized mobile-robot navigation scenarios and simulation testing.

Import documented operations from this namespace or its public submodules.
Exports are loaded on demand; importing NavProbe starts no CLI, GUI, or viewer.
The implementation and public API both live under this namespace.
"""
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("navprobe")
except PackageNotFoundError:
    __version__ = "0+uninstalled"

_EXPORTS = {
    "Corridor": "scenarios",
    "Scenario": "scenarios",
    "LoopScenario": "scenarios",
    "Terrain": "scenarios",
    "DungeonScenario": "scenarios",
    "MazeScenario": "scenarios",
    "StaticBox": "scenarios",
    "StaticObjectSettings": "scenarios",
    "ScenarioPreset": "scenarios",
    "load_preset": "scenarios",
    "parse_preset": "scenarios",
    "save_preset": "scenarios",
    "discover_presets": "scenarios",
    "populate_scenario": "scenarios",
    "static_objects": "scenarios",
    "placement_geometry": "scenarios",
    "sample_scenic": "scenarios",
    "GenerationContext": "generation",
    "GenerationPipeline": "generation",
    "generate_spec": "generation",
    "export_scene": "generation",
    "build_model": "simulation",
    "example_robot": "simulation",
    "load_scene": "simulation",
    "run": "simulation",
    "PlannedRoute": "navigation",
    "astar": "navigation",
    "plan_scenario": "navigation",
    "Controller": "controllers",
    "ControllerContext": "controllers",
}

__all__ = [*_EXPORTS, "__version__"]


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{module}", __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
