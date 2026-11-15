"""Environment generation and XML export; no viewer is started.

Convenience exports from the corresponding NavProbe implementation modules.
"""
from navprobe.simulation.generation import (
    GenerationContext,
    GenerationStage,
    GenerationPipeline,
    generate_spec,
    export_scene,
    ground_stage,
    walls_stage,
    static_objects_stage,
    lighting_stage,
)

__all__ = ['GenerationContext', 'GenerationStage', 'GenerationPipeline', 'generate_spec', 'export_scene', 'ground_stage', 'walls_stage', 'static_objects_stage', 'lighting_stage']
