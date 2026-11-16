"""Explicit optional desktop entry points; importing this module opens nothing."""
import importlib.util


def require_gui():
    if importlib.util.find_spec('PySide6') is None:
        raise ValueError('The GUI requires PySide6. Install it with: python -m pip install "navprobe[gui]" (or ".[gui]" from a checkout).')


def open_gui():
    require_gui()
    from .ui.editor import main
    return main(['navprobe'])


def preview_scenario(preset):
    require_gui()
    from .scenarios.library import ScenarioPreset
    if not isinstance(preset, ScenarioPreset):
        preset = ScenarioPreset('Scenario', '', preset)
    from PySide6.QtWidgets import QApplication
    from .ui.preview import TrackPreview
    app = QApplication.instance() or QApplication(['navprobe preview'])
    window = TrackPreview()
    window.setWindowTitle(preset.name)
    window.resize(800, 600)
    window.set_scenario(preset.scenario)
    window.show()
    return app.exec()
