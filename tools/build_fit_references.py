"""Build original fitted garment cages and isolated Meshy inputs from local measurements."""

import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.local' / 'semibot-preview'))
from measure_fit import SOURCE, bounds, local, transforms_for

OUTPUT = Path(sys.argv[-1]).resolve()
OUTPUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
SEGMENTS = 64


def fabric(name, rgb):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*[(x / 255) ** 2.2 for x in rgb], 1)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    shader = nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = material.diffuse_color
    shader.inputs['Roughness'].default_value = .79
    return material


IVORY = fabric('Ivory woven cloth', (233, 219, 193))
INNER = fabric('Inner lining', (174, 154, 126))
HONEY = fabric('Honey yellow', (226, 154, 38))
INK = fabric('Charcoal', (54, 46, 43))
PALETTE = [IVORY, INNER, HONEY, INK]


def tree(sources):
    vertices, faces = [], []
    for _, coords, tris in sources:
        first = len(vertices)
        vertices.extend(coords)
        faces.extend(tuple(first + v for v in tri) for tri in tris)
    return BVHTree.FromPolygons(vertices, faces, all_triangles=True)


def ring_coords(axis, height, theta, radius, center):
    a, b = math.cos(theta) * radius, math.sin(theta) * radius
    return Vector((a, height, b + center)) if axis == 'Y' else Vector((height, a, b))


def profile(sources, rows, clearance, axis='Y', center=0.0):
    surface = tree(sources)
    measured = []
    for height in rows:
        ring = []
        for i in range(SEGMENTS):
            theta = i * math.tau / SEGMENTS
            origin = ring_coords(axis, height, theta, 0, center)
            direction = ring_coords(axis, height, theta, 1, center) - origin
            hit, _, _, _ = surface.ray_cast(origin + 2 * direction, -direction, 2)
            ring.append((hit - origin).dot(direction) if hit is not None else None)
        measured.append(ring)
    result = []
    for index, ring in enumerate(measured):
        resolved = []
        for j, radius in enumerate(ring):
            if radius is None:
                candidates = [(abs(k-index), row[j]) for k, row in enumerate(measured) if row[j] is not None]
                radius = min(candidates)[1] if candidates else .04
            resolved.append(max(.025, radius + clearance))
        result.append(resolved)
    return result


def make_mesh(name, coords, faces, colors):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(coords, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    for mat in PALETTE:
        mesh.materials.append(mat)
    for i, face in enumerate(mesh.polygons):
        face.material_index = colors[i]
        face.use_smooth = True
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(mesh)
    bm.free()
    return obj


def shell(name, rows, radii, *, center=0.0, axis='Y', fill_top=False, fill_bottom=False, paint=None, detail=None):
    coords, faces, colors = [], [], []
    outer = len(rows) * SEGMENTS
    thickness = .006
    for inner in (False, True):
        for j, y in enumerate(rows):
            for i, radius in enumerate(radii[j]):
                angle = i * math.tau / SEGMENTS
                relief, vert = detail(j, angle) if detail else (0.0, 0.0)
                cap_offset = thickness * ((j == len(rows)-1 and fill_bottom) - (j == 0 and fill_top)) if inner else 0
                coords.append(ring_coords(axis, y + vert + cap_offset, angle, max(.01,radius + relief - (thickness if inner else 0)),center))
    for side in range(2):
        for j in range(len(rows)-1):
            for i in range(SEGMENTS):
                a = side*outer+j*SEGMENTS+i
                b = side*outer+j*SEGMENTS+(i+1)%SEGMENTS
                faces.append((a,b,b+SEGMENTS,a+SEGMENTS))
                colors.append(1 if side else (paint(j) if paint else 0))
    for ring, close in ((0,fill_top),(len(rows)-1,fill_bottom)):
        if close:
            for side in range(2):
                faces.append(tuple(side*outer+ring*SEGMENTS+i for i in range(SEGMENTS)))
                colors.append(1 if side else (paint(max(0,ring-1)) if paint else 0))
            continue
        for i in range(SEGMENTS):
            a = ring*SEGMENTS+i
            b = ring*SEGMENTS+(i+1)%SEGMENTS
            faces.append((a,b,b+outer,a+outer))
            colors.append(1)
    return make_mesh(name,coords,faces,colors)


def hole(obj, center_x, center_y, rx, ry):
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, depth=.39, radius=1, location=(center_x,center_y,.49))
    cutter = bpy.context.object
    cutter.scale.x, cutter.scale.y = rx, ry
    mod = obj.modifiers.new('Semibot eye opening','BOOLEAN')
    mod.operation, mod.solver, mod.object = 'DIFFERENCE','EXACT',cutter
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter,do_unlink=True)


def puff(name, center, scale, material):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=16,location=center)
    obj=bpy.context.object
    obj.name, obj.scale = name,scale
    obj.data.materials.append(material)
    for face in obj.data.polygons:
        face.use_smooth=True
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    return obj


def stem(name, a, b):
    a,b=Vector(a),Vector(b)
    obj=puff(name,(a+b)*.5,(.022,.022,(b-a).length*.62),INK)
    center=(a+b)*.5
    rotation=(b-a).normalized().to_track_quat('Z','Y')
    for v in obj.data.vertices:
        v.co=center+rotation@(v.co-center)
    return obj


head = ['player_head_top','player_head_bot_sphere','player_head_bot_flat']
hood_rows = [.391,.382,.365,.34,.305,.27,.23,.19,.15,.11,.07,.03,.005,-.024,-.06,-.10,-.145,-.19,-.235,-.275,-.31,-.34,-.368,-.387]
hood_radii = profile(local('Stand','Hood',head),hood_rows,.018,center=.244)
hood_radii[0]=[.031]*SEGMENTS
hood_radii[1]=[max(.033,.78*r) for r in hood_radii[2]]
hood_radii[-1]=[max(.05,.78*r) for r in hood_radii[-2]]
hood = shell('Closed ivory hood',hood_rows,hood_radii,center=.244,fill_top=True,
             detail=lambda j,a:(.0025*math.sin(a*6)*math.sin(j*math.pi/23),0))
for side in (-1,1):
    hole(hood,side*.1209,.1189,.099,.100)

upper_names=['player_body_top_sphere','player_body_top_flat']
bodice_rows=[.366,.350,.334,.314,.287,.255,.225,.198,.174,.149,.126,.103,.075,.047,.019,-.012,-.032]
bodice_radii=profile(local('Stand','Bodice',upper_names)+local('Crouch','Bodice',upper_names),bodice_rows,.019)
def bodice_fold(j,a):
    y=bodice_rows[j]
    front=max(0,math.sin(a))
    x=abs(math.cos(a))
    relief=.050*math.exp(-((y-.16)/.14)**2-((x-.37)/.26)**2)*front**3
    fold=.003*math.sin(a*9+.3)*((j+1)/len(bodice_rows))
    return relief+fold,0
bodice=shell('Contoured bodice',bodice_rows,bodice_radii,detail=bodice_fold)

hem_rows=[.315,.30,.28,.25,.22,.19,.155,.12,.085,.055,.025,-.002,-.027,-.042,-.056,-.074,-.095]
hem_radii=profile(local('Stand','Mantle',['player_body_bot']),hem_rows,.017)
bottom_upper_radii=profile(local('Stand','Bodice',upper_names),[y-.291 for y in hem_rows],.012)
for j,y in enumerate(hem_rows):
    if y>.0:
        hem_radii[j]=[max(a,b) for a,b in zip(hem_radii[j],bottom_upper_radii[j])]
def hem_detail(j,a):
    p=j/(len(hem_rows)-1)
    return (.006+ .013*p)*math.sin(a*9+.3)+.015*p, .012*p**3*math.sin(a*5+.15)
hem=shell('Close pleated striped hem',hem_rows,hem_radii,paint=lambda j:2 if j in (12,13) else 3 if j in (14,15) else 0,
          detail=hem_detail)

sleeve_rows=[.435,.425,.407,.385,.35,.315,.28,.245,.21,.175,.135,.085,.04,.0,-.052,-.077]
sleeve_radii=profile(local('Stand','Right Sleeve',['player_arm_R']),sleeve_rows,.012,axis='X')
sleeve=shell('Right tapered ivory sleeve',sleeve_rows,sleeve_radii,axis='X',
             detail=lambda j,a:(.009 if 0<j<3 else .003*math.sin(a*4+j*.3),0))

sock_rows=[.070,.032,-.012,-.055,-.105,-.158,-.213,-.265,-.316,-.36,-.404,-.445,-.48,-.513,-.538,-.550]
sock_radii=profile(local('Stand','Right Sock',['player_leg_R']),sock_rows,.012)
sock=shell('Right fitted bee stocking',sock_rows,sock_radii,fill_bottom=True,
           paint=lambda j:0 if j<6 else 2 if (j//2)%2==1 else 3)

antennae=[]
for side in (-1,1):
    a=(side*.107,.370,.245)
    b=(side*.145,.456,.228)
    c=(side*.196,.527,.220)
    antennae.extend([stem('Stem base',a,b),stem('Stem curve',b,c),puff('Honey felt tip',c,(.043,.047,.042),HONEY)])

parts={'01-antennae':antennae,'02-hood':[hood],'03-bodice':[bodice],
       '04-right-sleeve':[sleeve],'05-hem':[hem],'06-right-sock':[sock]}

tech={}
for key,items in parts.items():
    vertices=[v.co for obj in items for v in obj.data.vertices]
    fit_bounds=bounds(vertices)
    tech[key]={'bounds':fit_bounds,'size':[round(b-a,4) for a,b in zip(*fit_bounds)],
               'origin':[0,0,0], 'targetTriangles':dict(zip(parts,[400,1700,1600,850,1500,950]))[key]}
    print(key,tech[key],flush=True)
    for obj in items:
        for v in obj.data.vertices:
            x,y,z=v.co
            v.co=(x,-z,y)
        obj.data.update()

payload={'version':'0.3-fit','coordinateSystem':'Unity X right, Y up, Z forward; anchor-local units',
         'pieces':tech,'apertures':{'xCenters':[-.1209,.1209],'yCenter':.1189,'halfWidth':.099,'halfHeight':.100},
         'clearance':{'hood':.018,'bodice':.019,'hem':.017,'sleeve':.012,'sock':.012},
         'hemCrouch':{'sourceAnchor':'BodyBottom','persistentAnchor':'BodyTop','crouchTopY':.045,'crouchBottomY':-.128}}
(OUTPUT/'dimensions.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')

# The editable reference file contains only original garments. Stock game geometry never enters it.
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT/'Boobees-fit-references.blend'))


def aim(obj,center):
    obj.rotation_euler=(Vector(center)-obj.location).to_track_quat('-Z','Y').to_euler()


bpy.ops.object.camera_add()
camera=bpy.context.object
camera.data.type='ORTHO'
scene.camera=camera
for coord,power,size in [((-2,-3,3),210,3),((2,-1,2),140,2),((1,2,2),190,2)]:
    bpy.ops.object.light_add(type='AREA',location=coord)
    light=bpy.context.object
    light.data.energy=power
    light.data.shape='DISK'
    light.data.size=size
    aim(light,(0,0,0))
scene.world=bpy.data.worlds.new('Grey stage')
scene.world.color=(.18,.18,.18)
scene.render.engine='CYCLES'
scene.cycles.samples=10
scene.cycles.use_denoising=True
scene.render.film_transparent=True
scene.render.resolution_x=640
scene.render.resolution_y=640
scene.render.resolution_percentage=100
scene.render.image_settings.color_mode='RGBA'
angles={'hero':(.70,-2.75,1.2),'front':(0,-3,.24),'side':(3,0,.32),'back':(0,3,.36)}
for key,items in parts.items():
    folder=OUTPUT/key
    folder.mkdir(exist_ok=True)
    for candidate in parts.values():
        for obj in candidate:
            obj.hide_render=obj not in items
    points=[v.co for obj in items for v in obj.data.vertices]
    limits=bounds(points)
    center=Vector([(a+b)*.5 for a,b in zip(*limits)])
    extent=max(b-a for a,b in zip(*limits))
    camera.data.ortho_scale=extent*1.40
    for label,direction in angles.items():
        # A higher look angle exposes the opening on the sleeve and the skirt.
        if label=='hero' and key in ('04-right-sleeve','05-hem','06-right-sock'):
            direction=(.68,-2.55,1.72)
        camera.location=center+Vector(direction).normalized()*3
        aim(camera,center)
        scene.render.filepath=str(folder/f'{label}.png')
        bpy.ops.render.render(write_still=True)
