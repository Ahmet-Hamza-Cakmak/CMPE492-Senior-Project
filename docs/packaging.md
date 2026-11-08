# Building NavProbe

NavProbe is the distribution name and primary CLI command. The `navprobe`
namespace exposes scenario classes and `python -m navprobe`; the established
`robo_sim_py` implementation and `robo-sim-py` command remain compatible.

## Dependencies

- Base install: NumPy, MuJoCo, Shapely. No Qt or Scenic requirement.
- `[gui]`: PySide6, needed only for the editor and schematic preview.
- `[scenic]`: Scenic, needed to sample static objects or Scenic scenarios.
- `[all]`: both optional runtime integrations.
- `[dev]`: `build` and `twine`, needed for packaging checks.

A saved scenario with concrete object placements can be loaded and exported
without Scenic. GUI tests require `[gui]`, and sampling tests require `[scenic]`.
For the complete development test suite install `.[all,dev]`.
The Python minimum is 3.10. GitHub CI runs the complete suite on Linux with
Python 3.10 and 3.14; other platforms still need release testing. See
[CI and releases](ci.md) for checks and repository setup.

## Build and check

From the repository root, in a virtual environment:

```bash
python -m pip install -e ".[all,dev]"
python -m build
python -m twine check dist/*
python scripts/check_distribution.py
```

`build` creates a source distribution and builds the wheel from that source
archive. This checks that the source archive contains the necessary build inputs.
Build isolation normally installs the backend declared in `pyproject.toml`.
If the required backend is already installed, `python -m build --no-isolation`
is also supported for offline/local checks.

The archive checker expects one wheel and one source archive in `dist/`.
Move previous release artifacts out of that directory before building a new
version. Build artifacts and setuptools metadata are Git-ignored.

## Included resources and licensing

Explicit package-data patterns include robot XMLs, meshes, textures, robot
attribution documents, presets, and Scenic programs. The checker compares every
runtime source/resource file byte-for-byte with both distributions, inspects
metadata and extras, verifies CLI entry points and all three licence documents,
and rejects local reports, generated scenes, virtual environments, and caches.

Original source is MIT-licensed. The bundled Google Robot model/assets remain
Apache-2.0, reflected in the aggregate distribution expression
`MIT AND Apache-2.0`. Original-code licensing is not applied over upstream assets.
The source archive additionally contains tests, documentation, examples, and
the archive checker. The wheel contains the installable packages and runtime
resources, rather than development tests or local reports.

## Verify an installed artifact

Install the built wheel into a fresh virtual environment and run from a directory
outside the checkout. Check `navprobe --help`, `python -m navprobe`, preset discovery,
XML export, and both bundled robot model loads. With a base-only installation,
`navprobe --gui` and `navprobe preview` should explain how to install `[gui]`.
Install the optional extras to test the editor and Scenic sampling separately.

NavProbe is published on PyPI as an alpha release. The release workflow can
publish subsequent versions after Trusted Publishing is configured; ordinary CI
builds only retain downloadable artifacts. See [CI and releases](ci.md).

## Local verification record

The initial 0.1.0 artifacts were installed into a fresh temporary virtual
environment without GUI or Scenic, then exercised outside the repository.
Both bundled robot models loaded, all nine presets were discovered, maze XML
export succeeded, frozen static-object scenarios replayed without Scenic, and
GUI/preview commands reported the missing extra cleanly. The environment used
Python 3.14, MuJoCo 3.17, NumPy 2.5, and Shapely 2.2 on Linux. The development
suite additionally uses the locally installed optional integrations.
