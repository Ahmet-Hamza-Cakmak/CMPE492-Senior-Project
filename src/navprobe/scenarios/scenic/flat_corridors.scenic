# Flat-ground connected corridor family. Distances are metres, turns degrees.
# Each sample chooses 2–8 sections and one shared usable corridor width.
# Edit these distributions to change the family of generated environments.
param ground = "flat"
param corridor_count = DiscreteRange(2, 8)
corridorWidth = Range(0.8, 1.5)
param corridor_width = corridorWidth
param line_width = 0.025

# Scenic samples random quantities after constructing the model, so a random
# count cannot control a Python range() here. Sample eight candidates; the
# adapter keeps the first corridor_count entries.
param corridor_lengths = [Range(2.0, 4.0) for i in range(8)]
param corridor_angles = [0.0] + [Range(-75.0, 75.0) for i in range(7)]

require corridorWidth > 0.025
