"""Compatibility imports; population is shared by all generated scenarios."""
from .population import (placement_region, navigation_connected, scenic_boxes,
                         validate_objects, _sample, static_objects, populate_scenario)

dungeon_objects = static_objects
populate_dungeon = populate_scenario
