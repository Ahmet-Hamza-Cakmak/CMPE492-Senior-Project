"""MuJoCo geometry for flat BSP rooms and their connecting passages."""

import math

from ..scenarios.dungeon import dungeon_layout


def add_dungeon_ground(context):
    import mujoco

    spec, scenario, default = context.spec, context.scenario, context.default
    layout = dungeon_layout(scenario)
    x0,y0,x1,y1 = layout.bounds
    spec.worldbody.add_geom(default, name='environment_ground', type=mujoco.mjtGeom.mjGEOM_BOX,
                            pos=[(x0+x1)/2,(y0+y1)/2,-.025], size=[(x1-x0)/2,(y1-y0)/2,.025],
                            rgba=[.57,.65,.68,1], contype=1, conaffinity=1)
    for i,room in enumerate(layout.rooms):
        circular = room.shape == 'circular'
        spec.worldbody.add_geom(default, name=f'dungeon_room_{i}',
                                type=mujoco.mjtGeom.mjGEOM_CYLINDER if circular else mujoco.mjtGeom.mjGEOM_BOX,
                                pos=[room.x,room.y,.0002],
                                size=[room.width/2,.0002,0] if circular else [room.width/2,room.height/2,.0002],
                                rgba=[.9,.9,.9,1],contype=0,conaffinity=0)
    def strip(name,a,b,width,z,color):
        dx,dy=b[0]-a[0],b[1]-a[1]
        angle=math.atan2(dy,dx)
        spec.worldbody.add_geom(default,name=name,type=mujoco.mjtGeom.mjGEOM_BOX,
                                pos=[(a[0]+b[0])/2,(a[1]+b[1])/2,z],
                                size=[math.hypot(dx,dy)/2,width/2,.0002],
                                quat=[math.cos(angle/2),0,0,math.sin(angle/2)],rgba=color,contype=0,conaffinity=0)
    for i,path in enumerate(layout.passages):
        for j,(a,b) in enumerate(zip(path,path[1:])):
            strip(f'dungeon_passage_{i}_{j}',a,b,scenario.width,.0002,[.9,.9,.9,1])
        # Fill L-bend and endpoint squares to match the square-buffered footprint.
        for j,(x,y) in enumerate(path):
            spec.worldbody.add_geom(default,name=f'dungeon_join_{i}_{j}',type=mujoco.mjtGeom.mjGEOM_BOX,
                                    pos=[x,y,.0002],size=[scenario.width/2,scenario.width/2,.0002],
                                    rgba=[.9,.9,.9,1],contype=0,conaffinity=0)
    for i,(a,b) in enumerate(zip(layout.route,layout.route[1:])):
        strip(f'track_line_{i}',a,b,scenario.line_width,.0008,[.015,.015,.015,1])
