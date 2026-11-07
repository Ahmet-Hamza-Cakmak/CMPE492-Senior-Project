"""Versioned, data-only scenario presets, independent of the desktop toolkit."""

from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
import sys
import uuid

from . import Corridor, Scenario, LoopScenario, Terrain, DungeonScenario, MazeScenario


BUNDLED_DIRECTORY = Path(__file__).parent / "presets"


def user_scenario_directory():
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "line-tracker-sim" / "scenarios"


@dataclass(frozen=True)
class ScenarioPreset:
    name: str
    description: str
    scenario: Scenario | LoopScenario | DungeonScenario | MazeScenario

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 80:
            raise ValueError("Scenario name must contain 1–80 characters.")
        if not isinstance(self.description, str) or len(self.description) > 500:
            raise ValueError("Scenario description must be text of at most 500 characters.")

    def to_dict(self):
        from .population import populate_scenario
        from .objects import StaticObjectSettings
        scenario = populate_scenario(self.scenario)
        terrain = {"terrain": asdict(scenario.terrain)}
        population = {}
        if scenario.objects != StaticObjectSettings() or scenario.static_objects is not None:
            population = {"objects": asdict(scenario.objects),
                          "static_objects": None if scenario.static_objects is None else [asdict(obj) for obj in scenario.static_objects]}
        if isinstance(scenario, (MazeScenario, DungeonScenario)):
            values = asdict(scenario)
            if values["static_objects"] is not None:
                values["static_objects"] = list(values["static_objects"])
            return {"version": 4 if isinstance(scenario, MazeScenario) else 3,
                    "type": "maze" if isinstance(scenario, MazeScenario) else "dungeon",
                    "name": self.name, "description": self.description, **values}
        if isinstance(scenario, LoopScenario):
            return {"version": 2, "type": "loop", "name": self.name,
                    "description": self.description, "shape": scenario.shape,
                    "radius": scenario.radius, "width": scenario.width,
                    "line_width": scenario.line_width, **terrain, **population}
        return {
            "version": 1, "name": self.name, "description": self.description,
            "width": scenario.width, "line_width": scenario.line_width,
            "corridors": [{"length": part.length, "turn": part.turn} for part in scenario.corridors],
            **terrain, **population,
        }


def _population_fields(payload):
    from .objects import StaticObjectSettings, StaticBox
    settings = payload.get("objects", {})
    if not isinstance(settings, dict):
        raise ValueError("Object settings must be an object.")
    objects = StaticObjectSettings(**settings)
    saved = payload.get("static_objects")
    if saved is not None:
        if not isinstance(saved, list) or not all(isinstance(obj, dict) for obj in saved):
            raise ValueError("Static placements must be a list of box records.")
        saved = tuple(StaticBox(**obj) for obj in saved)
    return {"objects": objects, "static_objects": saved}


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number.")
    return float(value)


def load_preset(path):
    return parse_preset(json.loads(Path(path).read_text(encoding="utf-8")))


def parse_preset(payload):
    try:
        if not isinstance(payload, dict):
            raise ValueError("Scenario must be a JSON object.")
        if type(payload.get("version")) is not int or payload["version"] not in (1, 2, 3, 4):
            raise ValueError("Unsupported scenario version; expected version 1, 2, 3, or 4.")
        values = payload.get("terrain", {})
        if not isinstance(values, dict) or values.keys() - {"mode", "height", "spacing", "resolution", "seed"}:
            raise ValueError("Terrain must be an object with recognized parameters.")
        values = dict(values)
        for key in ("height", "spacing"):
            if key in values:
                values[key] = _number(values[key], key)
        terrain = Terrain(**values)
        population = _population_fields(payload)
        if payload["version"] == 4:
            from dataclasses import fields
            names = {field.name for field in fields(MazeScenario)}
            if payload.get("type") != "maze" or payload.keys() - (names | {"version", "type", "name", "description"}):
                raise ValueError("Version 4 requires a maze scenario with recognized fields.")
            values = {key: payload[key] for key in names - {"terrain", "objects", "static_objects"} if key in payload}
            return ScenarioPreset(payload["name"], payload.get("description", ""), MazeScenario(**values, terrain=terrain, **population))
        if payload["version"] == 3:
            from dataclasses import fields
            names = {field.name for field in fields(DungeonScenario)}
            if payload.get("type") != "dungeon" or payload.keys() - (names | {"version", "type", "name", "description"}):
                raise ValueError("Version 3 requires a dungeon scenario with recognized fields.")
            values = {key: payload[key] for key in names - {"terrain", "objects", "static_objects"} if key in payload}
            scenario = DungeonScenario(**values, terrain=terrain, **population)
            return ScenarioPreset(payload["name"], payload.get("description", ""), scenario)
        if payload["version"] == 2:
            allowed = {"version", "type", "name", "description", "shape", "radius", "width", "line_width", "terrain", "objects", "static_objects"}
            if payload.get("type") != "loop" or payload.keys() - allowed:
                raise ValueError("Version 2 requires a loop scenario with recognized fields.")
            scenario = LoopScenario(payload["shape"], _number(payload["radius"], "Radius"),
                                    _number(payload["width"], "Width"),
                                    _number(payload["line_width"], "Line width"), terrain, **population)
            return ScenarioPreset(payload["name"], payload.get("description", ""), scenario)
        allowed = {"version", "name", "description", "width", "line_width", "corridors", "terrain", "objects", "static_objects"}
        if payload.keys() - allowed:
            raise ValueError("Scenario contains unknown fields.")
        parts = payload["corridors"]
        if not isinstance(parts, list) or not 1 <= len(parts) <= 100:
            raise ValueError("Scenario must contain 1–100 corridors.")
        corridors = []
        for part in parts:
            if not isinstance(part, dict) or set(part) != {"length", "turn"}:
                raise ValueError("Each corridor must contain length and turn.")
            corridors.append(Corridor(_number(part["length"], "Length"),
                                      _number(part["turn"], "Turn")))
        scenario = Scenario(tuple(corridors), _number(payload["width"], "Width"),
                            _number(payload["line_width"], "Line width"), terrain, **population)
        return ScenarioPreset(payload["name"], payload.get("description", ""), scenario)
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError(f"Invalid scenario fields: {exc}") from exc


def discover_presets(directory):
    """Return usable presets and per-file errors; one bad file cannot hide others."""
    presets, errors = [], []
    for path in sorted(Path(directory).glob("*.json")):
        try:
            presets.append((path, load_preset(path)))
        except (OSError, ValueError) as exc:
            errors.append(f"{path.name}: {exc}")
    return presets, errors


def save_preset(preset, directory):
    """Add a new library entry without replacing an existing scenario."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4().hex}.json"
    with path.open("x", encoding="utf-8") as file:
        json.dump(preset.to_dict(), file, indent=2, allow_nan=False)
        file.write("\n")
    return path
