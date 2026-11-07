"""NavProbe: randomized mobile-robot navigation scenarios and simulation testing.

The established ``robo_sim_py`` modules remain available for existing Python
integrations. This namespace exposes the scenario API under the new name.
"""
from importlib.metadata import PackageNotFoundError, version

from robo_sim_py import Corridor, Scenario, LoopScenario, Terrain, DungeonScenario, MazeScenario

try:
    __version__ = version("navprobe")
except PackageNotFoundError:
    __version__ = "0+uninstalled"

__all__ = ["Corridor", "Scenario", "LoopScenario", "Terrain", "DungeonScenario", "MazeScenario", "__version__"]
