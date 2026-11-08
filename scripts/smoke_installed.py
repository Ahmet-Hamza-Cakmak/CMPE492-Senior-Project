"""Exercise an installed base wheel outside the checkout, without GUI or Scenic.

Run with a fresh environment's Python after installing the wheel. Uses temporary
outputs, loads MuJoCo models without a viewer, and never starts a controller.
"""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    import navprobe
    from navprobe import Corridor, MazeScenario, Scenario
    from robo_sim_py.assets import EXAMPLES
    from robo_sim_py.scenarios.library import BUNDLED_DIRECTORY, discover_presets
    from robo_sim_py.scenarios.objects import StaticBox, StaticObjectSettings
    from robo_sim_py.simulation import build_model, load_scene
    from robo_sim_py.simulation.generation import export_scene

    source = Path(__file__).resolve().parents[1] / 'src'
    assert not Path(navprobe.__file__).resolve().is_relative_to(source), 'Imported checkout instead of installed wheel'
    for optional in ('PySide6', 'scenic'):
        assert importlib.util.find_spec(optional) is None, f'{optional} unexpectedly installed in base environment'

    def cli(*arguments, code=0):
        result = subprocess.run([sys.executable, '-m', 'navprobe', *arguments],
                                capture_output=True, text=True, timeout=90)
        assert result.returncode == code, result.stdout + result.stderr
        return result.stdout + result.stderr

    for command in ((), ('generate',), ('run',), ('scenario',), ('preview',), ('validate',), ('list',)):
        assert 'usage:' in cli(*command, '--help')
    # Both installed console entry points remain available.
    for name in ('navprobe', 'robo-sim-py'):
        executable = Path(sys.executable).with_name(name)
        if not executable.exists():
            executable = Path(shutil.which(name) or '')
        subprocess.run([str(executable), '--help'], check=True, capture_output=True, timeout=30)
    assert 'simple_robot' in cli('list', 'robots')
    presets, errors = discover_presets(BUNDLED_DIRECTORY)
    assert presets and not errors, errors
    for example in EXAMPLES:
        assert build_model(example.path, MazeScenario(rows=3, columns=3)).ngeom > 0
    with tempfile.TemporaryDirectory(prefix='navprobe-wheel-smoke-') as directory:
        output = Path(directory) / 'maze.xml'
        cli('generate', '--maze', '--maze-rows', '3', '--maze-columns', '3', '--output', str(output))
        cli('validate', str(output))
        assert load_scene(output).ngeom > 0
        # Concrete placements need no Scenic installation to validate or export.
        saved = Scenario((Corridor(8),), width=2,
                         objects=StaticObjectSettings(count=1),
                         static_objects=(StaticBox(3, .5, .3, .3, .4),))
        assert load_scene(export_scene(saved, Path(directory) / 'saved-box.xml')).ngeom > 0
    for command in (('--gui',), ('preview',)):
        assert 'navprobe[gui]' in cli(*command, code=1)
    print(f'Installed NavProbe {navprobe.__version__}: CLI, presets, both robots, XML export, saved obstacles, and optional-dependency messages passed.')


if __name__ == '__main__':
    main()
