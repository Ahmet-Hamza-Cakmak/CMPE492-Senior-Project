# Installation

[Documentation index](README.md) · [Project README](../README.md)

Commands and source paths assume the repository root unless stated otherwise.

## Install and run

Python **3.10 or newer** is required. Scene generation and validation do not need
a desktop; the editor, schematic preview, and MuJoCo viewer need graphics support.
The current local validation environment uses Python 3.14 on Linux; other
supported versions and platforms still need release testing.

Install the alpha release from PyPI:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --pre navprobe  # CLI, geometry, and MuJoCo
navprobe --help
navprobe generate --maze --maze-rows 4 --maze-columns 4 --output maze.xml
```

Choose optional dependencies as needed:

```bash
python -m pip install --pre "navprobe[gui]"     # editor and schematic preview
python -m pip install --pre "navprobe[scenic]"  # constrained static-object sampling
python -m pip install --pre "navprobe[all]"     # both GUI and Scenic
navprobe --gui
```

The current release is `0.1.0a1`; APIs and behaviour may change during alpha
development. To install that exact release, use
`python -m pip install "navprobe[all]==0.1.0a1"`. To upgrade to the latest
available prerelease, use `python -m pip install --upgrade --pre "navprobe[all]"`.

On Windows activate with `.venv\Scripts\activate`.

## Install from source

From a local checkout, use `python -m pip install ".[all]"`. For development,
use `python -m pip install -e ".[all,dev]"` instead. You can also install directly
from GitHub (requires Git):

```bash
python -m pip install "navprobe[all] @ git+https://github.com/Ahmet-Hamza-Cakmak/CMPE492-Senior-Project.git"
```

To install a downloaded wheel, use
`python -m pip install /path/to/navprobe-0.1.0a1-py3-none-any.whl`.

## Commands and platform notes

`python -m navprobe` is equivalent to `navprobe`. Existing `robo-sim-py` commands,
`python -m robo_sim_py`, and Python imports from `robo_sim_py` remain supported.
The scenario API is also available as `from navprobe import MazeScenario`.
Installing the GUI extra is necessary for `--gui` and `preview`; opening a
MuJoCo simulation viewer itself does not require PySide6.

On macOS the application launches the MuJoCo worker using `mjpython`. On Linux,
Qt may require system graphics libraries; an `xcb-cursor` error on Ubuntu/Debian
can require `libxcb-cursor0`. An optional Python extra does not install operating
system graphics drivers or display servers.
