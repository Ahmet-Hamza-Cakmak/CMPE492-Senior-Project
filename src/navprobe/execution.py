"""Shared execution configuration, dispatch, and worker lifecycle.

Python applications use these services directly; CLI/GUI only adapt presentation
and process transport. Preparation never executes a supplied controller.
"""
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, fields, replace
import json
import math
from pathlib import Path
import subprocess
import sys
import uuid

from .services import ScenarioOptions, configure_scenario, resolve_robot
from .scenarios.library import ScenarioPreset, user_scenario_directory


@dataclass(frozen=True)
class RunOptions(ScenarioOptions):
    scene: str | Path | None = None
    package: str | Path | None = None
    auto_follow: bool | None = None
    navigation: str | None = None
    grid_resolution: float | None = None
    navigation_clearance: float | None = None
    simulation_speed: float = 1.
    menagerie: str | Path | None = None
    run_directory: str | Path | None = None
    trust_package: bool = False
    approved_sha256: str | None = None

    @classmethod
    def from_mapping(cls, values):
        names = {f.name for f in fields(cls)}
        return cls(**{key: value for key, value in values.items() if key in names})


@dataclass(frozen=True)
class RunRequest:
    """Prepared, reusable execution inputs. Creating one does not start execution."""
    options: RunOptions
    preset: ScenarioPreset | None = None
    robot_path: Path | None = None
    scene_path: Path | None = None
    package_path: Path | None = None
    package_mode: str | None = None
    approved_sha256: str | None = None
    run_directory: Path | None = None
    automatic: bool = False
    footprint: object = None
    warnings: tuple[str, ...] = ()

    @property
    def scenario(self):
        return self.preset.scenario if self.preset else None

    def worker_request(self):
        """Serialize only at the explicit CLI/GUI process boundary."""
        o = self.options
        arguments = ['-m', 'navprobe.simulation', '--simulation-speed', str(o.simulation_speed)]
        if self.package_path:
            arguments += ['--package', str(self.package_path), '--approved-sha256', self.approved_sha256]
            if o.menagerie:
                arguments += ['--menagerie', str(Path(o.menagerie).expanduser().resolve())]
            if self.run_directory:
                arguments += ['--run-directory', str(self.run_directory)]
        elif self.scene_path:
            arguments += ['--scene', str(self.scene_path)]
        else:
            arguments += ['--robot', str(self.robot_path)]
            if self.automatic:
                arguments += ['--auto-follow', '--navigation', o.navigation or 'auto']
                if o.grid_resolution is not None:
                    arguments += ['--grid-resolution', str(o.grid_resolution)]
                if o.navigation_clearance is not None:
                    arguments += ['--navigation-clearance', str(o.navigation_clearance)]
        payload = json.dumps(self.preset.to_dict(), allow_nan=False).encode() if self.preset else b''
        executable = str(Path(sys.executable).with_name('mjpython')) if sys.platform == 'darwin' else sys.executable
        return [executable, *arguments], payload


def _finite(value, name, minimum, maximum=math.inf):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be finite and between {minimum} and {maximum}.')


def prepare_run(options=None, **changes):
    """Validate and freeze a run without executing controllers or opening viewers."""
    if options is None:
        options = RunOptions()
    if not isinstance(options, RunOptions):
        raise TypeError('Expected RunOptions.')
    o = replace(options, **changes) if changes else options
    for key in ('robot', 'scene', 'package'):
        value = getattr(o, key)
        if value is not None and not isinstance(value, (str, Path)):
            raise TypeError(f'{key} must be a path or string.')
        if isinstance(value, str) and not value.strip():
            raise ValueError(f'{key} must not be empty.')
    if sum(value is not None for value in (o.robot, o.scene, o.package)) > 1:
        raise ValueError('Choose only one execution source: robot, scene, or package.')
    _finite(o.simulation_speed, 'simulation_speed', .1, 20)
    o = replace(o, simulation_speed=float(o.simulation_speed))
    if o.navigation not in (None, 'auto', 'line', 'astar'):
        raise ValueError('navigation must be auto, line, or astar.')
    if type(o.trust_package) is not bool:
        raise ValueError('trust_package must be a boolean.')
    if o.auto_follow is not None and type(o.auto_follow) is not bool:
        raise ValueError('auto_follow must be a boolean or None.')
    if o.grid_resolution is not None:
        _finite(o.grid_resolution, 'grid_resolution', 0)
        if o.grid_resolution == 0:
            raise ValueError('grid_resolution must be positive.')
    if o.navigation_clearance is not None:
        _finite(o.navigation_clearance, 'navigation_clearance', .25)
    nav = any(getattr(o, key) is not None for key in ('navigation', 'grid_resolution', 'navigation_clearance'))
    if nav and (o.scene or o.package):
        raise ValueError('Navigation options apply to generated tracks with registered robots; imported scenes/packages provide their own controller.')
    if (o.scene or o.package) and o.auto_follow is not None:
        raise ValueError('auto_follow applies only to generated tracks with a robot.')
    if not o.package and (o.trust_package or o.approved_sha256 or o.menagerie or o.run_directory):
        raise ValueError('Package options require a package.')
    source = ScenarioOptions.from_mapping(vars(o))
    # RunOptions.robot chooses the execution robot, not a layout override.
    has_layout = replace(source, robot=None).has_generation_settings()
    if o.scene:
        if has_layout:
            raise ValueError('Track options cannot modify an imported scene.')
        path = Path(o.scene).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f'Scene does not exist: {path}')
        return RunRequest(o, scene_path=path)
    if o.package:
        from .experiments import open_package
        path = Path(o.package).expanduser().resolve()
        with open_package(path, menagerie_directory=o.menagerie, expected_digest=o.approved_sha256) as experiment:
            if experiment.menagerie and not o.menagerie:
                raise ValueError('This package requires a menagerie directory.')
            if experiment.mode != 'robot' and has_layout:
                raise ValueError('Only robot packages accept generated track options.')
            if not o.trust_package:
                raise ValueError(f"Package '{experiment.name}' contains Python code that can access your files and network. SHA-256: {experiment.digest}. Inspect it, then set trust_package=True (--trust-package in the CLI).")
            if o.run_directory and experiment.mode != 'standalone':
                raise ValueError('run_directory is only supported for full ZIP packages with a standalone entry point.')
            destination = None
            if experiment.mode == 'standalone':
                if o.simulation_speed != 1:
                    raise ValueError('Full ZIP entry-point scripts own their simulation pacing.')
                destination = Path(o.run_directory or user_scenario_directory().parent/'runs'/uuid.uuid4().hex).expanduser().resolve()
            result = configure_scenario(source, robot_path=experiment.model_path) if experiment.mode == 'robot' else None
            return RunRequest(o, preset=result.preset if result else None, package_path=path,
                              package_mode=experiment.mode, approved_sha256=experiment.digest,
                              run_directory=destination, footprint=result.footprint if result else None,
                              warnings=result.warnings if result else ())
    from .assets import example_for_path, controller_mode
    robot = resolve_robot(o.robot)
    automatic = o.auto_follow if o.auto_follow is not None else example_for_path(robot) is not None
    if automatic and example_for_path(robot) is None:
        raise ValueError('Automatic driving requires a registered robot; use auto_follow=False for custom XML.')
    result = configure_scenario(source, robot_path=robot)
    if nav and not automatic:
        raise ValueError('Navigation options require automatic driving; remove --no-auto-follow / set auto_follow=True.')
    if automatic:
        mode = controller_mode(robot, result.scenario, o.navigation or 'auto')
        if mode != 'astar' and (o.grid_resolution is not None or o.navigation_clearance is not None):
            raise ValueError('Grid and navigation-clearance options require A* with the simple_robot on flat ground.')
    return RunRequest(o, preset=result.preset, robot_path=robot, automatic=automatic,
                      footprint=result.footprint, warnings=result.warnings)


def _request(value, changes):
    if isinstance(value, RunRequest):
        if changes:
            raise ValueError('A prepared RunRequest cannot be combined with option overrides; prepare a new request.')
        return value
    return prepare_run(value, **changes)


@contextmanager
def _resources(request):
    """Build execution resources once; keep imported files alive through cleanup."""
    from .simulation import build_model, load_scene
    from .experiments.controllers import load_controller, place_robot, BundledController, ControllerContext
    with ExitStack() as stack:
        controller, context = None, None
        if request.package_path:
            if not request.approved_sha256:
                raise ValueError('Packaged Python requires explicit approval of the ZIP hash.')
            from .experiments import open_package
            experiment = stack.enter_context(open_package(request.package_path,
                menagerie_directory=request.options.menagerie, expected_digest=request.approved_sha256))
            if experiment.mode == 'standalone':
                raise ValueError('Standalone entry-point scripts cannot be stepped as managed simulations; use run_experiment().')
            model = build_model(experiment.model_path, request.scenario) if request.scenario else load_scene(experiment.model_path)
            if request.scenario:
                place_robot(model, experiment.spawn)
            previous_path = sys.path[:]
            sys.path.insert(0, str(experiment.controller_path.parent))
            stack.callback(lambda: sys.path.__setitem__(slice(None), previous_path))
            def unload_controller_modules():
                for name, module in list(sys.modules.items()):
                    file = getattr(module, '__file__', None)
                    if file and Path(file).is_relative_to(experiment.root):
                        sys.modules.pop(name, None)
            stack.callback(unload_controller_modules)
            try:
                controller, context = load_controller(experiment, request.scenario)
            except SystemExit as exc:
                raise RuntimeError(f'Controller initialization requested process exit: {exc.code}.') from exc
        elif request.scene_path:
            model = load_scene(request.scene_path)
        else:
            model = build_model(request.robot_path, request.scenario)
            if request.automatic:
                o = request.options
                controller = BundledController(request.robot_path, mode=o.navigation or 'auto',
                    resolution=.25 if o.grid_resolution is None else o.grid_resolution, clearance=o.navigation_clearance)
                context = ControllerContext(request.robot_path.parent, {}, request.scenario, tuple(request.scenario.points()), None)
        try:
            yield model, controller, context
        except SystemExit as exc:
            raise RuntimeError(f'Controller requested process exit: {exc.code}.') from exc
        finally:
            if controller is not None:
                try:
                    controller.close()
                except SystemExit as exc:
                    raise RuntimeError(f'Controller cleanup requested process exit: {exc.code}.') from exc


def run_experiment(options=None, **changes):
    """Execute a prepared/generated/imported experiment with its normal viewer.

    Standalone full ZIP scripts execute their own entry point instead. Returns
    normally on success and propagates errors; it never parses CLI arguments.
    """
    request = _request(options, changes)
    if request.package_path and request.package_mode == 'standalone':
        from .experiments import open_package, run_full_zip
        if not request.approved_sha256:
            raise ValueError('Packaged Python requires explicit approval of the ZIP hash.')
        destination = request.run_directory or Path(request.options.run_directory or user_scenario_directory().parent/'runs'/uuid.uuid4().hex).expanduser().resolve()
        with open_package(request.package_path, menagerie_directory=request.options.menagerie,
                          expected_digest=request.approved_sha256) as experiment:
            try:
                run_full_zip(experiment, destination)
            except SystemExit as exc:
                if exc.code not in (None, 0):
                    raise RuntimeError(f'Experiment entry point exited with status {exc.code}.') from exc
        return destination
    from .simulation import run
    with _resources(request) as (model, controller, context):
        run(model, request.scenario, controller=controller, context=context,
            simulation_speed=request.options.simulation_speed, close_controller=False)
    return None


class SimulationSession:
    """Managed physics/controller session; no viewer, pacing, or automatic files.

    Use as a context manager, or explicitly close. Observations are available in
    ``model`` and ``data``; this is not a restricted sensor interface.
    """
    def __init__(self, request, *, controller=None, context=None):
        if controller is not None:
            if request.automatic or request.package_path:
                raise ValueError('Choose a Python controller with auto_follow=False and without a package.')
            for name in ('reset', 'step', 'close'):
                if not callable(getattr(controller, name, None)):
                    raise ValueError(f'Controller is missing {name}().')
        elif context is not None:
            raise ValueError('context requires a Python controller.')
        import mujoco
        self.request = request
        self._stack = ExitStack()
        self.closed = False
        try:
            self.model, self.controller, self.context = self._stack.enter_context(_resources(request))
            if controller is not None:
                from .experiments.controllers import ControllerContext
                self.controller = controller
                self.context = context if context is not None else ControllerContext(
                    request.robot_path.parent if request.robot_path else request.scene_path.parent,
                    {}, request.scenario, tuple(request.scenario.points()) if request.scenario else None, None)
                def close_python_controller():
                    try:
                        controller.close()
                    except SystemExit as exc:
                        raise RuntimeError(f'Controller cleanup requested process exit: {exc.code}.') from exc
                self._stack.callback(close_python_controller)
            self.data = mujoco.MjData(self.model)
            self.reset()
        except BaseException as exc:
            self.close()
            if isinstance(exc, SystemExit):
                raise RuntimeError(f'Controller reset requested process exit: {exc.code}.') from exc
            raise

    def _check_open(self):
        if self.closed:
            raise RuntimeError('Simulation session is closed.')

    def reset(self):
        self._check_open()
        import mujoco
        mujoco.mj_resetData(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        if self.controller:
            try:
                self.controller.reset(self.model, self.data, self.context)
            except SystemExit as exc:
                raise RuntimeError(f'Controller reset requested process exit: {exc.code}.') from exc
            mujoco.mj_forward(self.model, self.data)
        return self.data

    def step(self, steps=1):
        self._check_open()
        if type(steps) is not int or steps < 1:
            raise ValueError('steps must be a positive integer.')
        import mujoco
        for _ in range(steps):
            if self.controller:
                try:
                    self.controller.step(self.model, self.data, self.context)
                except SystemExit as exc:
                    raise RuntimeError(f'Controller step requested process exit: {exc.code}.') from exc
            mujoco.mj_step(self.model, self.data)
        return self.data

    def close(self):
        if not self.closed:
            self.closed = True
            self._stack.close()

    def __enter__(self):
        self._check_open()
        return self

    def __exit__(self, *exc):
        self.close()


def open_simulation(options=None, *, controller=None, context=None, **changes):
    """Create a headless session, optionally with a native Python controller.

    A supplied controller implements reset/step/close and requires auto_follow=False.
    It receives a default ControllerContext unless context is supplied explicitly.
    """
    return SimulationSession(_request(options, changes), controller=controller, context=context)


def start_worker(request):
    """Start an explicit worker transport tuple; return subprocess.Popen."""
    command, payload = request
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        process.stdin.write(payload)
        process.stdin.close()
    except BrokenPipeError:
        pass
    except BaseException:
        stop_simulation(process)
        raise
    return process


def start_simulation(options=None, **changes):
    """Launch asynchronously; return a Popen supporting poll()/wait()."""
    return start_worker(_request(options, changes).worker_request())


def stop_simulation(process):
    """Stop and reap an asynchronous worker; safe for None/already-exited workers."""
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def restart_simulation(process, options=None, **changes):
    """Prepare the replacement before stopping a working simulation."""
    request = _request(options, changes)
    stop_simulation(process)
    return start_worker(request.worker_request())
