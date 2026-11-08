# Continuous integration and releases

[Documentation index](README.md) · [Project README](../README.md)

## CI checks

`.github/workflows/ci.yml` runs on pull requests targeting `main`, pushes to
`main`, and manual dispatch from the Actions tab. It can also be called by the
release workflow.

- **Tests (Python 3.10 / 3.14):** install all runtime extras and run the complete
  unittest suite on Ubuntu 24.04. GUI tests use Qt's offscreen platform; Scenic
  integrations are installed so their tests are not skipped for a missing extra.
  These checks do not replace manual testing of a desktop viewer or Wayland.
- **Package and clean install:** build an sdist and a wheel from it, run strict
  Twine validation, and compare bundled sources/assets and licence notices with
  the checkout. Install the wheel in a clean base-only environment, then exercise
  CLI commands, presets, both robots, XML export/loading, frozen static placements,
  and optional-GUI error messages outside the checkout.
- **CI required:** succeeds only when every test-matrix job and the package job
  succeeds. Use this stable job name as the required merge check.

Checked wheel and sdist files are retained as `python-distributions` artifacts
for seven days. They are not uploaded to PyPI by CI. Workflows use read-only
repository permissions; external actions are pinned to commit hashes.

## Require checks before merging

A workflow reports results but does not itself block a merge. After its first
run, configure GitHub **Settings → Branches → Add branch protection rule** (or an
active branch ruleset) for `main`:

1. Require a pull request before merging. For solo development, no additional
   review approval is needed.
2. Require status checks before merging, selecting **CI required** from the CI
   workflow. Select the exact check name shown by the initial run.
3. Require the branch to be up to date before merging.
4. Apply the restriction to administrators / disable bypass if you want the same
   checks to apply to your own merges. Leave force pushes and deletion disabled.

Repository settings must be changed by an account with the appropriate access;
committing these workflow files does not enable branch protection automatically.
Once enforced, use branches and pull requests rather than direct pushes to main.

## Release-only PyPI publishing

`.github/workflows/publish.yml` starts only when a GitHub release is published,
including a published prerelease. Pushing a commit, merging a PR, or merely
pushing a tag does not publish a package.

Before the first automated publication:

1. Create a GitHub Actions environment named **pypi** in repository settings.
   If desired, add an approval gate and restrict deployment to release tags.
2. On PyPI, manage **navprobe → Publishing → Add a new publisher** with:
   - Owner: `Ahmet-Hamza-Cakmak`
   - Repository: `CMPE492-Senior-Project`
   - Workflow filename: `publish.yml`
   - Environment: `pypi`
3. These values must match exactly. No PyPI API token is stored in GitHub;
   the publish job requests short-lived credentials using Trusted Publishing.

For a new version:

1. Change the version in `pyproject.toml` and merge it through a passing PR.
2. Create a GitHub release from that main-branch commit, with a matching tag such
   as `v0.1.0a2` for package version `0.1.0a2`. Mark alpha/beta releases as prereleases.
3. Publish the GitHub release. The workflow verifies tag/version agreement and
   that the commit is in main's history, reruns CI, and publishes the exact
   artifacts produced by the package job after any environment approval.
4. Check the Actions result and PyPI installation before announcing the release.

Version `0.1.0a1` has already been published manually. Do not attempt to publish
it again: PyPI does not allow replacing existing release files. Use a new version
for the next release. Without the Trusted Publisher configuration, the upload
job will fail authentication; ordinary CI still works independently.

## Local checks

```bash
python -m pip install -e '.[all,dev]'
QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg python -m unittest discover -s tests -v
python -m build
python -m twine check --strict dist/*
python scripts/check_distribution.py
```

Use a clean `dist/` containing only the intended version. To run the installed
smoke check, install that wheel into a fresh base-only virtual environment and
run its Python against `scripts/smoke_installed.py` from a directory outside the
checkout. The smoke check intentionally requires GUI and Scenic to be absent.
