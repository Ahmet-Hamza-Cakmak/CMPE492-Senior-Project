# NavProbe

**Randomized navigation scenarios and simulation testing for mobile robots.**

Generate environments, place static obstacles with Scenic, and test robot
controllers in MuJoCo. Use the command line for repeatable experiments or the
optional graphical editor to configure and preview scenarios.

- Corridors, loops, BSP dungeons, and DFS/Prim/Growing Tree mazes.
- Configurable terrain, dimensions, seeds, and static obstacles.
- Saved scenarios and environment-only XML export.
- Bundled robots and imported robot/controller experiment packages.
- Obstacle-aware A* for the simple robot on supported flat layouts.

Dynamic obstacles and LoomRV runtime monitoring are planned extensions.

## Installation

Requires **Python 3.10+**. Generation and validation work without a desktop;
the graphical editor, preview, and simulation viewer require graphics support.

From a local checkout:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install ".[all]"
```

On Windows, activate with `.venv\Scripts\activate` instead.
Choose the installation that fits your workflow:

| Command | Includes |
| --- | --- |
| `pip install .` | CLI, geometry, and MuJoCo |
| `pip install ".[gui]"` | Base package plus graphical editor and preview |
| `pip install ".[scenic]"` | Base package plus constrained scenario sampling |
| `pip install ".[all]"` | Both GUI and Scenic |

To install a built wheel, use `pip install /path/to/navprobe-0.1.0-py3-none-any.whl`.
GitHub installation will be available once these changes reach the default branch:

```bash
python -m pip install "navprobe[all] @ git+https://github.com/Ahmet-Hamza-Cakmak/CMPE492-Senior-Project.git"
```

**The package has not been published to PyPI.** See the
[installation guide](docs/installation.md) for platform notes and compatibility.

## Quick start

Open the editor:

```bash
navprobe --gui
```

Generate a maze without opening a viewer:

```bash
navprobe generate --maze --maze-rows 4 --maze-columns 4 --output maze.xml
```

Run a small maze with static obstacles:

```bash
navprobe run --maze --maze-rows 4 --maze-columns 4 --static-objects 3 --simulation-speed 5
```

Use `navprobe --help`, `navprobe generate --help`, or `navprobe run --help` for
options. Running `navprobe` alone opens the interactive prompt.
`python -m navprobe` is equivalent; existing `robo-sim-py` commands and
`robo_sim_py` Python imports remain supported.

## Documentation

| Guide | Contents |
| --- | --- |
| [Installation](docs/installation.md) | Dependencies, optional extras, platform requirements |
| [CLI and simulation](docs/usage.md) | Commands, interactive prompt, importing scenes, exporting XML |
| [Scenarios and navigation](docs/scenarios.md) | Layouts, terrain, Scenic obstacles, seeds, A*, playback speed |
| [Experiment packages](docs/experiments.md) | Import formats and controller interfaces |
| [Development](docs/development.md) | Architecture, Python API, robot extensions, testing |
| [Packaging](docs/packaging.md) | Building and checking wheel/source distributions |

These guides are versioned with the code. Start at the
[documentation index](docs/README.md).

## Licence

Original project code is **MIT-licensed**. Bundled Google Robot model assets
retain **Apache-2.0**. See [LICENSE](LICENSE) and
[third-party notices](THIRD_PARTY_NOTICES.md).
