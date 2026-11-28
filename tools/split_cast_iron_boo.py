"""Split the published figure with surface cuts, retaining source coordinates and UVs."""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mesh_surface_clip import carve_convex

source_dir, out = (Path(value).resolve() for value in sys.argv[-2:])
out.mkdir(parents=True, exist_ok=True)
source = json.loads((source_dir/'source.json').read_text(encoding='utf-8'))
original = bpy.data.objects['Cast Iron Boo-Bee original']
material = original.data.materials[0]
verts = source['verts']
triangles = source['triangles']


def hull(points):
    def cross(a,b,c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    points=sorted(set(points))
    halves=[]
    for sequence in (points,list(reversed(points))):
        chain=[]
        for point in sequence:
            while len(chain)>1 and cross(chain[-2],chain[-1],point)<=0:
                chain.pop()
            chain.append(point)
        halves.extend(chain[:-1])
    return halves


def wing_planes(side, outline):
    # Silhouette positions were read from the rear orthographic render at scale 2.02.
    points=hull([((x-360)*2.02/720, (360-y)*2.02/720) for x,y in outline])
    planes=[lambda p: p[2]-.108]
    for (u,v),(s,t) in zip(points,points[1:]+points[:1]):
        def edge(p,a=u,b=v,dx=s-u,dy=t-v):
            return dx*(p[1]-b)-dy*(side*p[0]-a)
        planes.append(edge)
    return planes


upper_outline=[(444,269),(453,226),(464,194),(481,175),(507,154),(540,151),
               (561,173),(567,199),(568,219),(555,244),(536,261),(514,270),(463,283)]
lower_outline=[(445,267),(474,261),(519,253),(546,261),(565,276),(568,305),
               (552,329),(520,335),(491,328),(468,322),(450,299)]
regions=[('Pedestal', [lambda p: -.570-p[1]])]
for side in (-1,1):
    regions.append(('Antennae', [lambda p, sign=side: sign*p[0]-.093,
                                 lambda p, sign=side: .31-sign*p[0], lambda p: .15-p[2],
                                 lambda p, sign=side: p[1]+.45*(sign*p[0]-.12)-.691]))
    for outline in (upper_outline,lower_outline):
        regions.append(('Wings', wing_planes(side,outline)))
    regions.append(('Wings', [lambda p:p[1]-.424, lambda p:.573-p[1], lambda p:p[2]-.18,
                              lambda p, sign=side: sign*p[0]+.25*(p[1]-.45)-.278]))
regions += [('Hood',[lambda p:p[1]-.351]),('Bodice',[lambda p:p[1]+.080])]
parts = {name:[] for name in ('Antennae','Hood','Bodice','Hem','Wings','Pedestal')}
for source_tri in triangles:
    remaining=[[verts[index] for index in source_tri]]
    for name,planes in regions:
        next_polys=[]
        for poly in remaining:
            inside,outside=carve_convex(poly,planes)
            if inside:
                parts[name].append(inside)
            next_polys.extend(outside)
        remaining=next_polys
    parts['Hem'].extend(remaining)


def area(a,b,c):
    return (Vector(b[:3])-Vector(a[:3])).cross(Vector(c[:3])-Vector(a[:3])).length*.5


def assemble(name, polygons):
    points, indexed, faces = [],{},[]
    surface=0.0
    for poly in polygons:
        for i in range(1,len(poly)-1):
            triangle=poly[0],poly[i],poly[i+1]
            sq=area(*triangle)
            if sq<=1e-10:
                continue
            surface+=sq
            face=[]
            for point in triangle:
                key=tuple(round(v,8) for v in point)
                if key not in indexed:
                    indexed[key]=len(points)
                    points.append(point)
                face.append(indexed[key])
            faces.append((face[0],face[2],face[1]))
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata([(x,z,y) for x,y,z,*_ in points],[],faces)
    mesh.update()
    uv=mesh.uv_layers.new(name='Original UV')
    for loop in mesh.loops:
        uv.data[loop.index].uv=points[loop.vertex_index][-2:]
    mesh.materials.append(material)
    mesh.normals_split_custom_set_from_vertices([(x,z,y) for _,_,_,x,y,z,_,_ in points])
    for face in mesh.polygons:
        face.use_smooth=True
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    return obj, surface, points, faces


objects={}
before=sum(area(*(verts[j] for j in face)) for face in triangles)
after=0.0
geometry={}
for name,polygons in parts.items():
    obj,area_sum,points,faces=assemble(name,polygons)
    after+=area_sum
    objects[name]=obj
    low,high=([round(op(v[i] for v in points),5) for i in range(3)] for op in (min,max))
    geometry[name]={'sourceSpaceBounds':[low,high],'vertices':len(points),'triangles':len(faces)}
    print(name,geometry[name],flush=True)
assert math.isclose(before,after,rel_tol=3e-6), (before,after)
receipt={'asset':'Cast-Iron Boo-Bee, Boobees Valuables 0.2.15','coordinates':'Original BVB units in source-space bounds',
         'sourceTriangles':len(triangles),'sourceSurfaceArea':before,'combinedCutSurfaceArea':after,
         'sourceSpacePieces':geometry}
(out/'cut-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
bpy.data.objects.remove(original,do_unlink=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'Cast-Iron-Boo-Bee-cut.blend'))

for name,obj in objects.items():
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.export_scene.fbx(filepath=str(out/(name.lower()+'.fbx')),use_selection=True,
                             object_types={'MESH'},add_leaf_bones=False,path_mode='STRIP')

def aim(obj,location):
    obj.rotation_euler=(Vector(location)-obj.location).to_track_quat('-Z','Y').to_euler()

scene=bpy.context.scene
bpy.ops.object.camera_add()
camera=bpy.context.object
camera.data.type='ORTHO'
scene.camera=camera
for where, energy in [((-.8,-3,3),225),((2,-1,1),110),((-.5,3,2),190)]:
    bpy.ops.object.light_add(type='AREA',location=where)
    light=bpy.context.object
    light.data.energy=energy
    light.data.size=2.6
    aim(light,(0,0,0))
scene.world=bpy.data.worlds.new('Preview stage')
scene.world.color=(.19,.19,.19)
scene.render.engine='CYCLES'
scene.cycles.samples=12
scene.cycles.use_denoising=True
scene.render.film_transparent=True
scene.render.resolution_x=720
scene.render.resolution_y=720
scene.render.resolution_percentage=100
for name,obj in objects.items():
    for item in objects.values():
        item.hide_render=item!=obj
    u,v=geometry[name]['sourceSpaceBounds']
    center=Vector(((u[0]+v[0])*.5,(u[2]+v[2])*.5,(u[1]+v[1])*.5))
    camera.data.ortho_scale=max(b-a for a,b in zip(u,v))*1.25
    view=(.26,3,.6) if name=='Wings' else (.22,-3,.38)
    camera.location=center+Vector(view)
    aim(camera,center)
    scene.render.filepath=str(out/(name.lower()+'.png'))
    bpy.ops.render.render(write_still=True)

for item in objects.values():
    item.hide_render=False
camera.data.ortho_scale=1.96
camera.location=(0,-3,0)
aim(camera,(0,0,0))
scene.render.filepath=str(out/'reassembled.png')
bpy.ops.render.render(write_still=True)
