# Google Robot mobile example

Derived from the `google_robot/robot.xml` model and assets in
[MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie/tree/main/google_robot).
The upstream model and assets are licensed under Apache-2.0; see [LICENSE](LICENSE)
and the preserved [upstream README](UPSTREAM_README.md) for attribution and citation.

This adaptation changes the original fixed-base model:

- Adds a free joint to `base_link`.
- Moves the wheel visuals into independently driven wheel bodies.
- Replaces fixed wheel collision cylinders with rotating ellipsoid tires,
  radius 0.06435 m, with a 0.36566 m axle track.
- Adds bounded wheel torque actuators and low-friction front/rear support spheres.
- Assigns an approximate 35 kg base mass, center of mass at local z=0.25 m,
  and diagonal inertia (2, 2, 1) kg m². These are demonstration parameters,
  not identified hardware dynamics.
- Names the existing arm actuators so the controller can hold a neutral arm
  posture and slightly open fingers while driving.

The meshes and textures are unchanged and shipped locally; no separate Menagerie
checkout is needed after installation. The source checkout is not modified.

[controller.py](controller.py) configures the shared geometric tracking algorithm
for this base and commands the arm position servos. This uses perfect simulator
pose and known track geometry, not camera/reflectance measurements. It demonstrates
line tracing but is not a validated model of the real robot's navigation system.
