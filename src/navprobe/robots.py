"""Bundled robot registry and controller selection.

Convenience exports from the corresponding NavProbe implementation modules.
"""
from navprobe.assets import (
    EXAMPLES,
    RobotExample,
    register_robot,
    example_for_path,
    controller_mode,
    create_controller,
)

__all__ = ['EXAMPLES', 'RobotExample', 'register_robot', 'example_for_path', 'controller_mode', 'create_controller']
