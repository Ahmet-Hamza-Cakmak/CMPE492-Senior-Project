# Licensing and third-party notices

NavProbe's original source code is distributed under the MIT License in
`LICENSE`. Bundled third-party material retains its own licence; the MIT licence
does not replace the terms for those assets.

## Google Robot model and assets

The model and supporting assets under `src/robo_sim_py/assets/google_robot/`
are derived from Google DeepMind's MuJoCo Menagerie Google Robot model:

https://github.com/google-deepmind/mujoco_menagerie/tree/main/google_robot

The upstream robot model, meshes, and textures are distributed under Apache-2.0.
The complete licence is retained at
`src/robo_sim_py/assets/google_robot/LICENSE`. The upstream README and publication
attribution are preserved in `UPSTREAM_README.md`. Modifications to the robot
model are documented in `MODEL_NOTES.md`; the meshes and textures are unchanged.
These documents and the licence are included in both distribution formats.

The distribution's combined SPDX licence expression is `MIT AND Apache-2.0`:
MIT applies to original project code; Apache-2.0 applies to the bundled model
material. This is not a choice of either licence for every file.

## Installed dependencies

MuJoCo, NumPy, Shapely, optional PySide6, optional Scenic, and their dependencies
are installed separately and retain their respective licences. Their source
code or binary libraries are not vendored into the NavProbe wheel.
