"""Optional Scenic parameter sampling, independent of Qt and the simulator.

Scenic files are executable source code: load trusted files only. Sampling is
serialized because Scenic compilation and random generators use global state.
"""

from pathlib import Path
import random
import threading

from . import Corridor, Scenario, Terrain
from .library import ScenarioPreset

BUNDLED_SCENIC = Path(__file__).with_name("scenic") / "flat_corridors.scenic"
_SAMPLING_LOCK = threading.Lock()


def preset_from_parameters(parameters):
    """Translate one concrete Scenic sample into the existing scenario schema."""
    try:
        count = parameters["corridor_count"]
        lengths = parameters["corridor_lengths"]
        angles = parameters["corridor_angles"]
        if type(count) is not int or not 1 <= count <= 100:
            raise ValueError("corridor_count must be an integer from 1 to 100.")
        if len(lengths) < count or len(angles) < count:
            raise ValueError("Scenic must supply lengths and angles for every corridor.")
        if parameters["ground"] != "flat":
            raise ValueError("This Scenic adapter supports flat ground only.")
        scenario = Scenario(
            tuple(Corridor(float(lengths[i]), float(angles[i])) for i in range(count)),
            width=float(parameters["corridor_width"]),
            line_width=float(parameters["line_width"]), terrain=Terrain("flat"),
        )
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError(f"Invalid Scenic corridor parameters: {exc}") from exc
    return ScenarioPreset("Scenic flat corridors", "Sampled flat-ground corridors; shared width in metres, relative turns in degrees.", scenario)


def sample_scenic(path=BUNDLED_SCENIC, *, seed=42, max_iterations=2000):
    """Sample once and return an editable/exportable ScenarioPreset.

    Neither compilation nor sampling launches a viewer or simulation. The seed
    controls Scenic sampling, independently of the terrain seed in normal tracks.
    """
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise ValueError("Scenic seed must be an integer from 0 to 2147483647.")
    if type(max_iterations) is not int or max_iterations <= 0:
        raise ValueError("Scenic sampling limit must be a positive integer.")
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Scenic file does not exist: {path}")
    try:
        import scenic
        import numpy as np
    except ImportError as exc:
        raise ValueError('Scenic support is optional. Install it with: python -m pip install -e ".[scenic]"') from exc
    with _SAMPLING_LOCK:
        python_state, numpy_state = random.getstate(), np.random.get_state()
        try:
            random.seed(seed)
            np.random.seed(seed)
            specification = scenic.scenarioFromFile(str(path))
            scene, _ = specification.generate(maxIterations=max_iterations)
            return preset_from_parameters(scene.params)
        except Exception as exc:
            raise ValueError(f"Cannot sample Scenic scenario {path.name}: {exc}") from exc
        finally:
            random.setstate(python_state)
            np.random.set_state(numpy_state)
