# Line tracker simulation

A Python package with a desktop form that builds consecutive line-tracking corridors and opens a MuJoCo simulation with your robot.

## Install and run

Requires Python 3.10 or newer and a desktop with OpenGL support.

```bash
python -m pip install "git+https://github.com/Ahmet-Hamza-Cakmak/CMPE492-Senior-Project.git"
line-tracker-sim
```

The GitHub command works once these changes are pushed to the repository's default branch. For a local checkout:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .
python -m line_tracker_sim
```

On Windows activate with `.venv\Scripts\activate`. On Ubuntu/Debian, Tkinter may require `sudo apt install python3-tk`. On macOS use `mjpython -m line_tracker_sim` for MuJoCo's passive viewer.

## Create a scenario

1. Select your robot's main MJCF XML, or use the bundled example robot.
2. Set the number of corridors and click **Apply count**.
3. Enter each corridor's length in metres and its turn in degrees relative to the previous corridor. The first corridor starts at `(0, 0)` and faces +X; its turn is fixed at zero. Positive turns go left, negative turns go right, and zero continues straight.
4. Optionally change the corridor and black line widths.
5. Leave **Sample robot: automatically follow the line** checked to drive the bundled robot, or uncheck it for manual actuator control. This option is disabled for custom robot files.
6. Click **Open MuJoCo simulation**. The sample robot starts after a brief settling period, follows the track, slows for corners, and brakes near the final endpoint. Close the viewer to return to the form.

The corridors are flat white strips with black center lines, without walls. Consecutive strips share endpoints and have filled round joins, so there are no gaps even at turns. Sharp turns and self-intersections are allowed; intersecting tracks can create ambiguous routes for a future controller. The black line is visual and does not affect wheel contact.

## Robot files

Select a complete MJCF model with a `<mujoco>` root. Keep any included XML, meshes, and textures at the paths referenced by that model; the loader reads from its original directory using MuJoCo's [model editing API](https://mujoco.readthedocs.io/en/stable/python.html#model-editing). There is no need to select each asset separately. Missing assets or invalid models are reported in the form. Source model files are never modified.

Use a robot-only model without its own floor or scenery. The generated floor surface is at z=0. Position the robot at `(0, 0)` with the correct body height for its wheels and orient its forward direction along +X. Model poses, actuators and sensors are retained. A mobile robot needs a free joint or suitable planar joints; a fixed robot stays fixed.

The bundled robot includes two driven wheels, front and rear low-friction supports, motor actuators, and a sensor mounting site. Its automatic controller uses **ideal geometric sensing**: the known, ordered track center line and MuJoCo's robot pose. It steers toward a point 12 cm ahead on the route and controls wheel speeds through bounded motor torques. Motion comes from wheel contact and physics, without teleporting the robot or setting its pose.

This is a baseline path-following controller, **not a camera or reflectance sensor simulation**. It has no perception noise and knows the route through intersections. It slows for heading errors, stops within roughly 5 cm of the endpoint, and brakes if it strays more than 30 cm from the current section. Resetting the simulation resets controller progress. The controller is tuned for the bundled robot's 4 cm wheel radius and 14 cm axle width; custom robots still require their own control integration.

Straight routes, left/right 90° turns, a 135° turn, and a three-section route are covered by physics tests. Extremely short sections, narrow corridors, and other sharp/self-overlapping layouts are not guaranteed to be traversable by this robot.

After updating the source, reinstall before launching (or use `python -m pip install -e .` during development):

```bash
python -m pip install .
python -m line_tracker_sim
```

## Python API and verification

```python
from line_tracker_sim import Corridor, Scenario
from line_tracker_sim.simulation import build_model, example_robot

scenario = Scenario((Corridor(2), Corridor(1.5, 90), Corridor(2, -45)))
model = build_model(example_robot(), scenario)
```

Run headless tests after installation with `python -m unittest discover -s tests`. These check geometry, validation, model loading, actual driving through turns, endpoint braking, and controller reset; opening the GUI requires a display.

The broader research proposal remains in [ReadME.txt](ReadME.txt).
