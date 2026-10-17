"""Validated A2-style experiment packages. Inspection never imports user Python."""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

MAX_ARCHIVE = 256 * 1024 * 1024
MAX_EXPANDED = 1024 * 1024 * 1024


def relative_path(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('Package paths must be relative paths using forward slashes.')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError(f'Unsafe package path: {value}')
    return path


@dataclass(frozen=True)
class Experiment:
    root: Path
    name: str
    mode: str
    model_path: Path | None
    controller_path: Path
    config: dict
    route_path: Path | None
    spawn: tuple
    menagerie: bool
    digest: str


def read_manifest(root, digest=''):
    file = root / 'experiment.json'
    if file.stat().st_size > 1024 * 1024:
        raise ValueError('experiment.json is too large.')
    try:
        obj = json.loads(file.read_text(encoding='utf-8'))
        allowed = {'version', 'name', 'mode', 'scene', 'robot', 'controller', 'config', 'route', 'spawn', 'menagerie'}
        if not isinstance(obj, dict) or obj.keys() - allowed:
            raise ValueError('experiment.json contains unknown fields.')
        if type(obj.get('version')) is not int or obj['version'] != 1:
            raise ValueError('Experiment version must be 1.')
        mode = obj.get('mode')
        if mode not in ('full', 'robot'):
            raise ValueError('Experiment mode must be full or robot.')
        name = obj.get('name')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise ValueError('Experiment name must contain 1–100 characters.')
        if ('robot' if mode == 'full' else 'scene') in obj:
            raise ValueError('Specify scene for full experiments, or robot for robot experiments; not both.')

        def required_file(key, suffix=None):
            path = root / relative_path(obj[key])
            if not path.is_file() or (suffix and path.suffix.lower() != suffix):
                raise ValueError(f'{key} must reference an existing {suffix or "data"} file: {obj[key]}')
            return path

        model = required_file('scene' if mode == 'full' else 'robot', '.xml')
        controller = required_file('controller', '.py')
        config = obj.get('config', {})
        if not isinstance(config, dict):
            raise ValueError('Controller config must be a JSON object.')
        spawn = obj.get('spawn', [0, 0, 0, 0])
        if not isinstance(spawn, list) or len(spawn) != 4 or not all(
                type(v) in (int, float) and math.isfinite(v) for v in spawn):
            raise ValueError('spawn must be [x, y, z_offset, yaw_degrees], all finite numbers.')
        if mode == 'full' and any(spawn):
            raise ValueError('Full experiments define starting poses in their scene XML.')
        menagerie = obj.get('menagerie', False)
        if type(menagerie) is not bool:
            raise ValueError('menagerie must be true or false.')
        route = required_file('route') if 'route' in obj else None
        return Experiment(root, name, mode, model, controller, config, route, tuple(spawn), menagerie, digest)
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'Invalid experiment.json: {exc}') from exc


@contextmanager
def open_package(path, *, menagerie_directory=None, expected_digest=None):
    """Extract into an isolated temporary folder; remove it after the run ends.

    Accept files at ZIP root or within one enclosing assignment directory.
    Limits, path checks and link rejection protect extraction, not controller execution.
    """
    path = Path(path).expanduser()
    with path.open('rb') as stream:
        blob = stream.read(MAX_ARCHIVE + 1)
    if len(blob) > MAX_ARCHIVE:
        raise ValueError('ZIP exceeds the 256 MiB compressed size limit.')
    digest = hashlib.sha256(blob).hexdigest()
    if expected_digest is not None and digest != expected_digest:
        raise ValueError('The ZIP changed after approval. Select and approve the current package again.')
    with tempfile.TemporaryDirectory(prefix='line-tracker-experiment-') as directory:
        root = Path(directory) / 'experiment'
        root.mkdir()
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                entries = archive.infolist()
                if len(entries) > 10000 or sum(info.file_size for info in entries) > MAX_EXPANDED:
                    raise ValueError('ZIP exceeds 10,000 entries or 1 GiB expanded size.')
                files = {}
                directories = []
                seen = set()
                for info in entries:
                    rel = relative_path(info.filename.rstrip('/'))
                    kind = stat.S_IFMT(info.external_attr >> 16)
                    if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or info.flag_bits & 1:
                        raise ValueError('ZIP links, special files and encrypted entries are unsupported.')
                    if str(rel).casefold() in seen:
                        raise ValueError(f'Duplicate ZIP path: {rel}')
                    seen.add(str(rel).casefold())
                    if info.is_dir():
                        directories.append(rel)
                    else:
                        files[rel] = info
                manifests = [rel for rel in files if rel.name == 'experiment.json']
                if manifests:
                    if len(manifests) != 1 or len(manifests[0].parts) > 2:
                        raise ValueError('ZIP needs one experiment.json at its root or inside one assignment folder.')
                    prefix = manifests[0].parent
                else:
                    candidates = [rel.parent.parent for rel in files
                                  if rel.parts[-2:] == ('python', 'main.py') and len(rel.parts) <= 3]
                    if len(candidates) != 1:
                        raise ValueError('ZIP needs python/main.py at its root or inside one assignment folder.')
                    prefix = candidates[0]
                    if not any(rel.is_relative_to(prefix / 'scenes') and rel.suffix.lower() == '.xml' for rel in files):
                        raise ValueError('Assignment ZIP needs at least one XML file in scenes/.')
                for rel in directories:
                    if prefix != PurePosixPath('.') and not rel.is_relative_to(prefix):
                        raise ValueError('All ZIP files must be inside the assignment folder.')
                    (root / rel.relative_to(prefix)).mkdir(parents=True, exist_ok=True)
                for rel, info in files.items():
                    if prefix != PurePosixPath('.') and not rel.is_relative_to(prefix):
                        raise ValueError('All ZIP files must be inside the assignment folder.')
                    target = root / rel.relative_to(prefix)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open('xb') as output:
                        shutil.copyfileobj(source, output)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as exc:
            raise ValueError(f'Cannot unpack ZIP: {exc}') from exc
        experiment = (read_manifest(root, digest) if manifests else
                      Experiment(root, path.stem, 'standalone', None, root / 'python' / 'main.py',
                                 {}, None, (0, 0, 0, 0), False, digest))
        if menagerie_directory and (experiment.menagerie or experiment.mode == "standalone"):
            external = Path(menagerie_directory).expanduser().resolve()
            if not external.is_dir():
                raise ValueError('Select an existing mujoco_menagerie directory.')
            (root.parent / 'mujoco_menagerie').symlink_to(external, target_is_directory=True)
            if experiment.mode == 'standalone':
                local = root / 'mujoco_menagerie'
                if local.exists():
                    raise ValueError('ZIP already contains mujoco_menagerie; leave the external folder unset.')
                local.symlink_to(external, target_is_directory=True)
        yield experiment


def run_assignment(experiment, run_directory):
    """Execute the standard entry point in the worker; retain inputs and outputs."""
    import os
    import runpy
    import sys

    destination = Path(run_directory).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()  # Never overwrite a previous experiment.
    root = destination / 'assignment'
    shutil.copytree(experiment.root, root, symlinks=True)
    external = experiment.root.parent / 'mujoco_menagerie'
    if external.is_symlink():
        (destination / 'mujoco_menagerie').symlink_to(external.resolve(), target_is_directory=True)
    entry = root / 'python' / 'main.py'
    old_cwd, old_argv, old_path = Path.cwd(), sys.argv[:], sys.path[:]
    print(f'Experiment files: {root}', flush=True)
    try:
        os.chdir(root)
        sys.argv = [str(entry)]
        sys.path.insert(0, str(entry.parent))
        sys.path.insert(1, str(root))
        runpy.run_path(str(entry), run_name='__main__')
    finally:
        os.chdir(old_cwd)
        sys.argv[:] = old_argv
        sys.path[:] = old_path
