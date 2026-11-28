"""Fit the two Meshy garment candidates to their Unity anchor-local bounds."""

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

raw, output, dimensions = (Path(value).resolve() for value in sys.argv[-3:])
output.mkdir(exist_ok=True,parents=True)
spec = json.loads(dimensions.read_text(encoding='utf-8'))['pieces']
bpy.ops.wm.read_factory_settings(use_empty=True)


def fabric(name, rgb):
    color = bpy.data.materials.new(name)
    color.diffuse_color = (*[(v / 255) ** 2.2 for v in rgb], 1)
    return color


mats = [fabric('Ivory woven cloth',(233,219,193)), fabric('Honey yellow',(226,154,38)), fabric('Charcoal',(54,46,43))]


def face_count(obj):
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def local_bounds(obj):
    points = [(v.co.x,v.co.z,-v.co.y) for v in obj.data.vertices]
    return [[round(fn(p[i] for p in points),5) for i in range(3)] for fn in (min,max)]


receipt={}
for piece,part in [('sleeve','04-right-sleeve'),('sock','06-right-sock')]:
    start=set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(raw/f'meshy-right-{piece}.fbx'))
    obj, = [o for o in bpy.data.objects if o not in start and o.type=='MESH']
    obj.name=f'right-{piece}'
    obj.data.transform(obj.matrix_world)
    obj.matrix_world.identity()
    before=face_count(obj)
    if piece=='sleeve':
        # Meshy placed the broad shoulder opening on +X. The right arm's wrist is +X.
        for vert in obj.data.vertices:
            vert.co.x=-vert.co.x
        obj.data.flip_normals()
    count=spec[part]['targetTriangles']
    bpy.context.view_layer.objects.active=obj
    if before>count:
        modifier=obj.modifiers.new('Triangle budget','DECIMATE')
        modifier.ratio=count/before
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    measured=local_bounds(obj)
    target=spec[part]['bounds']
    for vert in obj.data.vertices:
        p=(vert.co.x,vert.co.z,-vert.co.y)
        fitted=[lo+(coord-a)*(hi-lo)/(b-a) for coord,a,b,lo,hi in zip(p,*measured,*target)]
        vert.co=(fitted[0],-fitted[2],fitted[1])
    obj.data.update()
    assert face_count(obj)<=count
    assert all(abs(a-b)<1e-4 for x,y in zip(local_bounds(obj),target) for a,b in zip(x,y))
    obj.data.materials.clear()
    for mat in mats:
        obj.data.materials.append(mat)
    if piece=='sock':
        edges=[-.158,-.232,-.306,-.380,-.454]
        for face in obj.data.polygons:
            height=sum(obj.data.vertices[i].co.z for i in face.vertices)/len(face.vertices)
            bands=sum(height<edge for edge in edges)
            face.material_index=(1+(bands+1)%2) if bands else 0
    # A center ray records whether topology leaves an unobstructed opening at the cuff.
    mesh=obj.data
    bvh=BVHTree.FromPolygons([v.co for v in mesh.vertices],[tuple(f.vertices) for f in mesh.polygons])
    origin=(target[0][0]-.05,0,0) if piece=='sleeve' else (0,0,target[1][1]+.05)
    direction=(1,0,0) if piece=='sleeve' else (0,0,-1)
    hit,_,_,travel=bvh.ray_cast(Vector(origin),Vector(direction),1.0)
    receipt[piece]={'generatedTriangles':before,'fittedTriangles':face_count(obj),'rightBounds':local_bounds(obj),
                    'cuffCenterRayDistance':round(travel,5) if hit is not None else None}
    mirror=obj.copy()
    mirror.data=obj.data.copy()
    mirror.name=f'left-{piece}'
    bpy.context.scene.collection.objects.link(mirror)
    for vert in mirror.data.vertices:
        vert.co.x=-vert.co.x
    mirror.data.flip_normals()
    for asset in (obj,mirror):
        bpy.ops.object.select_all(action='DESELECT')
        asset.select_set(True)
        bpy.context.view_layer.objects.active=asset
        bpy.ops.export_scene.fbx(filepath=str(output/f'{asset.name}.fbx'),use_selection=True,object_types={'MESH'},add_leaf_bones=False)

(output/'fit-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(receipt,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(output/'Meshy-garments.blend'))
