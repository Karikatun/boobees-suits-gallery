"""Clean the figure cuts and open two circular Semibot eye apertures."""

import collections
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mesh_surface_clip import carve_convex

output = Path(sys.argv[-1]).resolve()
output.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
hood = bpy.data.objects['Hood']
antennae = bpy.data.objects['Antennae']
mat = hood.data.materials[0]
cut_eyes = (-.085, .085)
eye_z = .5255
eye_radius = .070
roots = (-.120, .120)
root_y = -.054
root_radius = (.068, .080)


def triangles(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    return [tuple((*mesh.vertices[mesh.loops[k].vertex_index].co, *mesh.corner_normals[k].vector,
                   *mesh.uv_layers.active.data[k].uv) for k in tri.loops) for tri in mesh.loop_triangles]


def bake_mesh(obj, polygons):
    # Weld by position while keeping the original per-corner UVs and normals.
    points, indices, faces, uv, normals = [], {}, [], [], []
    for poly in polygons:
        for j in range(1, len(poly) - 1):
            tri = (poly[0], poly[j], poly[j + 1])
            if (Vector(tri[1][:3]) - Vector(tri[0][:3])).cross(Vector(tri[2][:3]) - Vector(tri[0][:3])).length < 1e-10:
                continue
            face = []
            for p in tri:
                key = tuple(round(x, 6) for x in p[:3])
                if key not in indices:
                    indices[key] = len(points)
                    points.append(p[:3])
                face.append(indices[key])
            if len(set(face)) < 3:
                continue
            faces.append(face)
            uv.extend(p[-2:] for p in tri)
            normals.extend(p[3:6] for p in tri)
    mesh = bpy.data.meshes.new(obj.name + ' Clean')
    mesh.from_pydata(points, [], faces)
    mesh.update()
    mesh.materials.append(mat)
    layer = mesh.uv_layers.new(name='Original UV')
    for slot, coords in zip(layer.data, uv):
        slot.uv = coords
    for poly in mesh.polygons:
        poly.use_smooth = True
    # Use the interpolated source normals at the modified edge and original normals elsewhere.
    mesh.normals_split_custom_set(normals)
    obj.data = mesh


def ellipse(x, other, rx, ry, second, segments):
    offset = math.cos(math.pi / segments)
    return [lambda p, a=math.cos((i + .5) * math.tau / segments), b=math.sin((i + .5) * math.tau / segments):
            offset - a * (p[0] - x) / rx - b * (p[second] - other) / ry for i in range(segments)]


def subtract(polygons, planes):
    result = []
    for p in polygons:
        _, keep = carve_convex(p, planes)
        result.extend(keep)
    return result


original = triangles(hood)
native_verts = [v.co.copy() for v in hood.data.vertices]
native_faces = [tuple(f.vertices) for f in hood.data.polygons]
native_triangles = [tuple(hood.data.uv_layers.active.data[k].uv.to_3d() for k in f.loop_indices)
                    for f in hood.data.polygons]
native_bvh = BVHTree.FromPolygons(native_verts, native_faces, all_triangles=True)
image = next(node.image for node in mat.node_tree.nodes if node.type == 'TEX_IMAGE' and node.image.name == 'color.png')
im_width, im_height = image.size
pixels = np.asarray(image.pixels[:], dtype='f').reshape((im_height, im_width, 4))


def neutral_uv(positions):
    candidates = []
    for x, z in positions:
        hit, _, idx, _ = native_bvh.ray_cast(Vector((x, -1, z)), Vector((0, 1, 0)), 1)
        if hit is None:
            continue
        u, v, _ = barycentric_transform(hit, *(native_verts[i] for i in native_faces[idx]), *native_triangles[idx])
        i, j = round(u * im_width), round(v * im_height)
        patch = pixels[j-15:j+16, i-15:i+16, :3]
        if patch.shape[:2] != (31, 31) or patch.sum(axis=2).min() < 1.3:
            continue
        score = float(patch.std(axis=(0, 1)).sum())
        candidates.append((score, u, v))
    assert candidates, 'Cloth donor region missing'
    _, u, v = min(candidates)
    return u, v


donor = neutral_uv([(x, z) for x in (-.022, -.012, 0, .012, .023) for z in (.566,.582,.612,.640,.660)] +
                   [(x, z) for x in (-.21,-.19,-.17,.17,.19,.21) for z in (.44,.47,.515,.553,.58)])


def repair(p, x, coord, second, scale=.11):
    return (*p[:6], donor[0] + (p[0]-x) * scale, donor[1] + (p[second]-coord) * scale)


hood_panels = list(original)
for x in roots:
    hood_panels = subtract(hood_panels, [lambda p: p[2]-.550, *ellipse(x, root_y, *root_radius, 1, 48)])
for side in (-1,1):
    # Fragments of the fused wing root project behind the cloth near mid-ear height.
    hood_panels = subtract(hood_panels, [lambda p: p[1]-.157, lambda p: p[2]-.356,
                                        lambda p, s=side: s*p[0]-.235])
    hood_panels = subtract(hood_panels, [lambda p: p[1]-.226, lambda p: p[2]-.348,
                                        lambda p, s=side: s*p[0]-.216])

# Recover crown cut boundaries, independent of the UV seams in the source mesh.
edges = collections.defaultdict(list)
for poly in hood_panels:
    for a, b in zip(poly, poly[1:]+poly[:1]):
        ka, kb = tuple(round(x,6) for x in a[:3]), tuple(round(x,6) for x in b[:3])
        if ka != kb:
            edges[tuple(sorted((ka,kb)))].append((a,b))
boundary = [pair[0] for pair in edges.values() if len(pair) == 1]
coords = list({tuple(round(v,5) for v in p[:3]): p[:3] for poly in hood_panels for p in poly}.values())


def crown_patch(center_x):
    def near_rim(p):
        r = math.hypot((p[0]-center_x)/root_radius[0], (p[1]-root_y)/root_radius[1])
        return .996 < r < 1.004 and p[2] > .550

    rim = {tuple(round(q,6) for q in p[:3]): p for pair in boundary for p in pair if near_rim(p)}
    points = sorted(rim.values(),key=lambda p: math.atan2((p[1]-root_y)/root_radius[1],(p[0]-center_x)/root_radius[0]))
    assert len(points) > 12, (center_x,len(points))
    # Fit the neighboring crown surface while respecting the exact positions around the new edge.
    def features(dx,dy): return (1,dx,dy,dx*dx,dx*dy,dy*dy)
    rows, values = [],[]
    for x,y,z in coords:
        dx,dy = x-center_x,y-root_y
        if math.hypot(dx,dy)<.145 and z>.575:
            weight = math.exp(-((dx*dx+dy*dy)/.012))
            rows.append(np.asarray(features(dx,dy))*weight)
            values.append(z*weight)
    coeff = np.linalg.lstsq(rows, values, rcond=None)[0]

    def at(dx,dy,offset=0):
        z = float(np.dot(coeff,features(dx,dy))) + offset
        _,a,b,c,d,e = coeff
        normal = Vector((-(a+2*c*dx+d*dy),-(b+d*dx+2*e*dy),1)).normalized()
        return repair((center_x+dx,root_y+dy,z,*normal),center_x,root_y,1)

    rings = []
    for ratio in (1.0,.64,.31):
        ring = []
        for p in points:
            dx,dy = p[0]-center_x,p[1]-root_y
            correction = (p[2]-float(np.dot(coeff,features(dx,dy))))*ratio**2
            ring.append(repair(p,center_x,root_y,1) if ratio==1 else at(dx*ratio,dy*ratio,correction))
        rings.append(ring)
    result = []
    for outside,inside in zip(rings,rings[1:]):
        for j in range(len(points)):
            k=(j+1)%len(points)
            result.append((outside[j],outside[k],inside[k],inside[j]))
    center = at(0,0)
    for a,b in zip(rings[-1],rings[-1][1:]+rings[-1][:1]):
        result.append((center,a,b))
    return result


for x in roots:
    hood_panels += crown_patch(x)

for cx in cut_eyes:
    # Reuse nearby ivory atlas texels on the portions of the old oval outside the new circle.
    cleaned = []
    for polygon in hood_panels:
        painted, cloth = carve_convex(polygon, [lambda p: -.133-p[1], *ellipse(cx,eye_z,.060,.093,2,48)])
        cleaned.extend(cloth)
        if painted:
            cleaned.append(tuple(repair(p,cx,eye_z,2) for p in painted))
    hood_panels = subtract(cleaned, [lambda p: -.133-p[1], *ellipse(cx,eye_z,eye_radius,eye_radius,2,72)])

# A tiny gold mark from the old face remains just left of the bridge; restore the ivory texels there.
cleaned = []
for panel in hood_panels:
    marked, cloth = carve_convex(panel, [lambda p: -.16-p[1], *ellipse(-.024,.544,.020,.019,2,32)])
    cleaned.extend(cloth)
    if marked:
        cleaned.append(tuple(repair(p,-.024,.544,2) for p in marked))
bake_mesh(hood,cleaned)

# Keep exactly the stalk components. This also handles older cuts that retained two wing flakes.
panels = triangles(antennae)
links = collections.defaultdict(set)
key = lambda p: tuple(round(v, 6) for v in p[:3])
for poly in panels:
    a,b,c=map(key,poly)
    for p in (a,b,c):
        links[p].update((a,b,c))
pending = set(links)
stalks = []
while pending:
    root = pending.pop()
    group, queue = {root}, [root]
    while queue:
        for p in links[queue.pop()] & pending:
            pending.remove(p)
            queue.append(p)
            group.add(p)
    if max(p[2] for p in group) > .79 and max(abs(p[0]) for p in group) < .31:
        stalks.append(group)
assert len(stalks)==2
keep = set().union(*stalks)
bake_mesh(antennae,[p for p in panels if key(p[0]) in keep])


def offset_stats(obj):
    obj.data.calc_loop_triangles()
    points=[(v.co.x,v.co.z,v.co.y) for v in obj.data.vertices]
    return {'vertices':len(points), 'triangles':len(obj.data.loop_triangles),
            'sourceSpaceBounds':[[round(fn(p[i] for p in points),5) for i in range(3)] for fn in (min,max)]}


receipt = {'Hood':offset_stats(hood), 'Antennae':offset_stats(antennae), 'eyeCenters':[[x,eye_z] for x in cut_eyes],
           'eyeRadius':eye_radius, 'eyePlane':'Source-space X / height', 'antennaComponents':len(stalks)}
(output/'cleanup-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(receipt),flush=True)
bpy.ops.wm.save_as_mainfile(filepath=str(output/'Cast-Iron-Boo-Bee-cut.blend'))
for obj, name in ((hood,'hood'),(antennae,'antennae')):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.export_scene.fbx(filepath=str(output/f'{name}.fbx'),use_selection=True,
                             object_types={'MESH'},add_leaf_bones=False,path_mode='STRIP')


def aim(obj,target):
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()


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
scene.cycles.samples=16
scene.cycles.use_denoising=True
scene.render.film_transparent=True
scene.render.resolution_x=720
scene.render.resolution_y=720
scene.render.resolution_percentage=100
for obj, name, direction in ((hood,'hood',(0,-3,.14)),(hood,'hood-three-quarter',(1.4,-3,.75)),(antennae,'antennae',(.22,-3,.38))):
    for candidate in scene.objects:
        if candidate.type=='MESH':
            candidate.hide_render=candidate!=obj
    center=Vector([(min(v.co[i] for v in obj.data.vertices)+max(v.co[i] for v in obj.data.vertices))*.5 for i in range(3)])
    extent=max(max(v.co[i] for v in obj.data.vertices)-min(v.co[i] for v in obj.data.vertices) for i in range(3))
    camera.data.ortho_scale=extent*1.23
    camera.location=center+Vector(direction)
    aim(camera,center)
    scene.render.filepath=str(output/f'{name}.png')
    bpy.ops.render.render(write_still=True)
