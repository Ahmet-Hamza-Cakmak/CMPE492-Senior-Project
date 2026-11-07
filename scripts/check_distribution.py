"""Check built archives against the actual runtime source and asset tree.

Run from a checkout: python scripts/check_distribution.py
Uses only the standard library; does not import GUI, Scenic, or MuJoCo.
"""
import configparser
from email.parser import BytesParser
from pathlib import Path
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def check():
    wheels = sorted((ROOT / 'dist').glob('navprobe-*.whl'))
    sources = sorted((ROOT / 'dist').glob('navprobe-*.tar.gz'))
    if len(wheels) != 1 or len(sources) != 1:
        raise SystemExit('Expected exactly one NavProbe wheel and one source distribution in dist/.')
    expected = {}
    for package in ('navprobe', 'robo_sim_py'):
        for path in (ROOT / 'src' / package).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.pyo'):
                expected[path.relative_to(ROOT / 'src').as_posix()] = path.read_bytes()
    with zipfile.ZipFile(wheels[0]) as archive:
        wheel = {name: archive.read(name) for name in archive.namelist() if not name.endswith('/')}
    with tarfile.open(sources[0], 'r:gz') as archive:
        sdist = {}
        for member in archive.getmembers():
            if member.isfile():
                sdist[member.name.split('/', 1)[1]] = archive.extractfile(member).read()
    for name, content in expected.items():
        if wheel.get(name) != content or sdist.get('src/' + name) != content:
            raise SystemExit(f'Runtime file missing or changed in distribution: {name}')
    metadata_paths = [name for name in wheel if name.endswith('.dist-info/METADATA')]
    if len(metadata_paths) != 1:
        raise SystemExit('Expected one wheel METADATA file.')
    metadata = BytesParser().parsebytes(wheel[metadata_paths[0]])
    assert metadata['Name'] == 'navprobe'
    assert metadata['Requires-Python'] == '>=3.10'
    assert metadata['License-Expression'] == 'MIT AND Apache-2.0'
    extras = set(metadata.get_all('Provides-Extra'))
    assert {'gui', 'scenic', 'all', 'dev'} <= extras
    requirements = metadata.get_all('Requires-Dist')
    assert all('extra ==' in line for line in requirements if line.lower().startswith(('pyside6', 'scenic')))
    assert any(line.lower().startswith('pyside6') and 'gui' in line for line in requirements)
    assert any(line.lower().startswith('scenic') and 'scenic' in line for line in requirements)
    base_requirements = [line for line in requirements if ';' not in line]
    assert len(base_requirements) == 3, base_requirements
    info = metadata_paths[0].rsplit('/', 1)[0]
    entrypoints = configparser.ConfigParser()
    entrypoints.read_string(wheel[info + '/entry_points.txt'].decode())
    assert entrypoints['console_scripts']['navprobe'] == 'robo_sim_py.cli:main'
    assert entrypoints['console_scripts']['robo-sim-py'] == 'robo_sim_py.cli:main'
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'src/robo_sim_py/assets/google_robot/LICENSE'):
        content = (ROOT / name).read_bytes()
        assert wheel.get(info + '/licenses/' + name) == content, name
        assert sdist.get(name) == content, name
    for name in (*wheel, *sdist):
        parts = Path(name).parts
        assert not any(part in ('.venv', '.venv~', '__pycache__', '.git', 'report') for part in parts), name
        assert not Path(name).name.startswith('report-v2.'), name
        assert name not in ('dungeon.xml', 'populated.xml', 'challenge.xml'), name
    # Development/rebuild resources belong in the sdist, not the installed wheel.
    for name in ('pyproject.toml', 'MANIFEST.in', 'scripts/check_distribution.py', 'docs/packaging.md'):
        assert name in sdist, name
    assert any(name.startswith('tests/') for name in sdist)
    print(f'Validated {len(expected)} runtime files in both archives, including all models, meshes, textures, presets, and Scenic programs.')
    print('Metadata, optional dependencies, entry points, licence texts, and source exclusions passed.')
    print(wheels[0].name)
    print(sources[0].name)


if __name__ == '__main__':
    check()
