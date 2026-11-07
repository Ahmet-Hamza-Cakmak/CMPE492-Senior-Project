# Python generates the layout first and supplies its available regions.
# These are spatial Scenic objects, not Python-generated candidate positions.
param placement_region = None
param object_count = 0
param min_size = 0.25
param max_size = 0.6
param object_height = 0.4
param object_clearance = 0.1
param first_region = None
param connectivity_check = None

available = globalParameters.placement_region
count = globalParameters.object_count
low = globalParameters.min_size
high = globalParameters.max_size
boxHeight = globalParameters.object_height
gap = globalParameters.object_clearance
firstRegion = globalParameters.first_region
isPassable = globalParameters.connectivity_check
workspace = Workspace(available)

boxes = []
for i in range(count):
    region = firstRegion if i == 0 else available
    obstacle = new Object in region,
        with width Range(low, high),
        with length Range(low, high),
        with height boxHeight,
        facing Range(-180, 180) deg
    boxes.append(obstacle)

# Conservative bounding-circle separation guarantees a footprint gap.
for i in range(count):
    for j in range(i):
        a = boxes[i]
        b = boxes[j]
        require (distance from a to b) >= (a.width**2 + a.length**2)**0.5/2 + (b.width**2 + b.length**2)**0.5/2 + gap

# Reject samples which disconnect the mission anchors for the configured radius.
require isPassable(boxes)
