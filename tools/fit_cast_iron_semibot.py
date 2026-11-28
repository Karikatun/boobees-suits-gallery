"""Fit the cleaned Cast-Iron Boo-Bee cuts to the two extracted Semibot poses."""

import argparse
import bisect
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import delaunay_2d_cdt
from mathutils.kdtree import KDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.local' / 'semibot-preview'))
from measure_fit import SOURCE, local, transforms_for

parser = argparse.ArgumentParser()
parser.add_argument('output', type=Path)
parser.add_argument('--draft', action='store_true')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=True)

POSES = ('Stand', 'Crouch')
PARTS = ('Hood', 'Bodice')
HEAD = ('player_head_top', 'player_head_bot_sphere', 'player_head_bot_flat')
TORSO = ('player_body_top_sphere', 'player_body_top_flat', 'player_body_bot',
         'player_health_LED', 'player_health_frame')
EYES = ('player_eye_L', 'player_eye_R')
SEAM = .351
SOURCE_EYE_Y = .5255
SOURCE_EYE_X = .085
SOURCE_RADIUS = .070
seam_height = -.201


def stage(p):
    return Vector((p.x, -p.z, p.y))


def raw(p):
    return Vector((p.x, p.z, -p.y))


def mix(a, b, factor):
    return a + (b - a) * factor


def smooth(lo, hi, x):
    t = min(1., max(0., (x - lo) / (hi - lo)))
    return t * t * (3 - 2 * t)


def interpolate(knots, x):
    i = max(0, min(bisect.bisect_right(knots, (x, math.inf)) - 1, len(knots) - 2))
    a, ya = knots[i]
    b, yb = knots[i + 1]
    return mix(ya, yb, (x - a) / (b - a))


def soften_max(a, b, width):
    h = max(0.0, width - abs(a - b)) / width
    return max(a, b) + width * h * h * .25


def tree(verts, faces):
    return BVHTree.FromPolygons(verts, faces, all_triangles=True, epsilon=0)


def closest_hit(trees, start, direction, distance):
    hit = None
    for collider in trees:
        p, _, _, d = collider.ray_cast(start, direction, distance)
        if p is not None:
            hit, distance = p, d
    return hit


def stock_material(name):
    if name.startswith('player_iris'):
        rgb, rough = (40, 45, 51), .34
    elif name.startswith('player_eye'):
        rgb, rough = (231, 235, 235), .30
    elif name == 'player_health_LED':
        rgb, rough = (58, 47, 40), .60
    elif name.startswith(('player_arm', 'player_leg', 'player_head_bot', 'player_health_frame')):
        rgb, rough = (103, 121, 130), .55
    else:
        rgb, rough = (133, 151, 159), .54
    return material('Native • ' + name, rgb, rough)


def material(name, rgb, roughness):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    shader = m.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*[(x / 255.) ** 2.2 for x in rgb], 1)
    shader.inputs['Roughness'].default_value = roughness
    return m


source = {name: bpy.data.objects[name] for name in PARTS}
scene = bpy.context.scene
scene.render.engine = 'CYCLES'


def prepare_mesh(name, obj, positions):
    # Resolve the cut mesh's T junctions before the cloth is bent out of its original plane.
    with bpy.context.temp_override(object=obj, active_object=obj):
        if obj.data.has_custom_normals:
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.000025)
    uv = bm.loops.layers.uv.active
    searchable = positions[name] + [
        p for other in PARTS if other != name for p in positions[other] if abs(p.z - SEAM) < .00001
    ]
    index = KDTree(len(searchable))
    for i, p in enumerate(searchable):
        index.insert(p, i)
    index.balance()
    for edge in list(bm.edges):
        start, end = edge.verts
        vector = end.co - start.co
        length = vector.length
        if length < .0002:
            continue
        steps = []
        for p, _, _ in index.find_range((start.co + end.co) * .5, length * .5 + .000035):
            fraction = (p - start.co).dot(vector) / vector.length_squared
            if (.000045 / length < fraction < 1 - .000045 / length
                    and (p - start.co - vector * fraction).length < .000029):
                steps.append(fraction)
        if not steps:
            continue
        original_uv = {
            face: {loop.vert: loop[uv].uv.copy() for loop in face.loops if loop.vert in (start, end)}
            for face in edge.link_faces
        }
        current, last = start, 0.
        for f in sorted(steps):
            if (f - last) * length < .000045:
                continue
            new_edge, v = bmesh.utils.edge_split(edge, current, (f - last) / (1 - last))
            if end not in edge.verts:
                edge = new_edge
            for loop in v.link_loops:
                coords = original_uv[loop.face]
                loop[uv].uv = coords[start].lerp(coords[end], f)
            current, last = v, f
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.000042)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    if name == 'Hood':
        long_edges = [e for e in bm.edges if e.calc_length() > .034
                      and not all(abs(v.co.z - SEAM) < .00001 for v in e.verts)]
        bmesh.ops.subdivide_edges(bm, edges=long_edges, cuts=1, use_grid_fill=True)
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
    for face in bm.faces:
        face.smooth = True
    if args.draft:
        boundaries = {edge for edge in bm.edges if edge.is_boundary}
        while boundaries:
            queue = [boundaries.pop()]
            vertices, edges = set(), set()
            while queue:
                edge = queue.pop()
                edges.add(edge)
                for v in edge.verts:
                    vertices.add(v)
                    for e in v.link_edges:
                        if e in boundaries:
                            boundaries.remove(e)
                            queue.append(e)
            if len(vertices) >= 12:
                print('BOUNDARY', name, len(vertices), len(edges),
                      [(round(min(v.co[i] for v in vertices),4), round(max(v.co[i] for v in vertices),4))
                       for i in range(3)], flush=True)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


original_positions = {name: [v.co.copy() for v in obj.data.vertices] for name, obj in source.items()}
for name, obj in source.items():
    prepare_mesh(name, obj, original_positions)


def assembly_boundaries():
    bm = bmesh.new()
    for obj in source.values():
        verts = [bm.verts.new(v.co) for v in obj.data.vertices]
        for f in obj.data.polygons:
            bm.faces.new([verts[i] for i in f.vertices])
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.000055)
    pending = {e for e in bm.edges if e.is_boundary}
    while pending:
        edge = pending.pop()
        start, current = edge.verts
        points = [start.co.copy()]
        while current != start:
            points.append(current.co.copy())
            neighbor = next((e for e in current.link_edges if e in pending), None)
            if neighbor is None:
                break
            pending.remove(neighbor)
            current = neighbor.other_vert(current)
        if len(points) >= 4:
            if args.draft:
                print('ASSEMBLY', len(points), 'closed', start == current,
                      [(round(min(p[i] for p in points),4), round(max(p[i] for p in points),4))
                       for i in range(3)], flush=True)
            if start == current:
                yield points
    bm.free()


def cloth_donor():
    mesh = source['Hood'].data
    tex = next(n.image for n in mesh.materials[0].node_tree.nodes
               if n.type == 'TEX_IMAGE' and n.image.name == 'color.png')
    width, height = tex.size
    pixels = np.asarray(tex.pixels[:], dtype=np.float32).reshape((height, width, 4))
    candidates = []
    uv = mesh.uv_layers.active
    for f in mesh.polygons:
        center = f.center
        if .42 < center.z < .64 and center.y > .10 and abs(center.x) < .14:
            coord = sum((uv.data[i].uv for i in f.loop_indices), Vector((0, 0))) / len(f.loop_indices)
            x, y = round(coord.x * width), round(coord.y * height)
            sample = pixels[max(0, y-27):y+27, max(0, x-27):x+27, :3]
            if sample.size and sample.sum(axis=2).min() > 1.10:
                candidates.append((abs(sample.mean() - .67) + sample.std() * .7, coord))
    return min(candidates, key=lambda t: t[0])[1]


def patch_wing_notches(boundaries):
    scars = [loop for loop in boundaries if all(p.y > .08 for p in loop)
             and max(p.z for p in loop) - min(p.z for p in loop) > .004]
    assert len(scars) >= 2
    donor = cloth_donor()
    panels = bmesh.new()
    uv = panels.loops.layers.uv.new('Original UV')
    for rim in scars:
        projected = [Vector((math.atan2(p.x, p.y) * .34, p.z)) for p in rim]
        n = len(projected)
        boundary = list(range(n))
        if sum(projected[i].cross(projected[(i+1) % n]) for i in range(n)) < 0:
            boundary.reverse()
        ring = np.array([tuple(q) for q in projected])
        radii = np.array([math.hypot(p.x, p.y) for p in rim])
        lo, hi = ring.min(axis=0), ring.max(axis=0)
        grid = [Vector((x, y)) for x in np.arange(lo[0] + .01, hi[0], .022)
                for y in np.arange(lo[1] + .012, hi[1], .022)
                if np.min(np.linalg.norm(ring - (x, y), axis=1)) > .008]
        coords, _, faces, ids, _, _ = delaunay_2d_cdt(projected + grid, [], [boundary], 1, .000008)
        vertices = []
        for point, origins in zip(coords, ids):
            source_i = next((i for i in origins if i < n), None)
            if source_i is not None:
                coord = rim[source_i].copy()
            else:
                distances = np.linalg.norm(ring - tuple(point), axis=1)
                weights = 1 / (distances ** 3 + .000003)
                A = np.column_stack((ring - tuple(point), np.ones(n)))
                radius = np.linalg.lstsq(A * weights[:, None], radii * weights, rcond=None)[0][2]
                radius = np.clip(radius, radii.min() - .012, radii.max() + .012)
                angle = point.x / .34
                coord = Vector((radius * math.sin(angle), radius * math.cos(angle), point.y))
            vertices.append(panels.verts.new(coord))
        center = Vector(((lo[0]+hi[0])*.5, (lo[1]+hi[1])*.5))
        for indices in faces:
            face = panels.faces.new([vertices[i] for i in indices])
            face.normal_update()
            c = face.calc_center_median()
            if face.normal.dot(Vector((c.x, c.y, 0))) < 0:
                face.normal_flip()
            face.smooth = True
            for loop in face.loops:
                p = loop.vert.co
                xy = Vector((math.atan2(p.x, p.y) * .34, p.z))
                loop[uv].uv = donor + (xy - center) * .125
    bmesh.ops.bisect_plane(panels, geom=[*panels.verts, *panels.edges, *panels.faces],
                          dist=.000015, plane_co=(0, 0, SEAM), plane_no=(0, 0, 1), use_snap_center=True)
    bmesh.ops.triangulate(panels, faces=list(panels.faces))
    for name in PARTS:
        obj = source[name]
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        uv_dest = bm.loops.layers.uv.active
        translated = {}
        for f in panels.faces:
            if (f.calc_center_median().z > SEAM) != (name == 'Hood'):
                continue
            for v in f.verts:
                if v not in translated:
                    translated[v] = bm.verts.new(v.co)
            face = bm.faces.new([translated[v] for v in f.verts])
            face.smooth = True
            for dest, src in zip(face.loops, f.loops):
                dest[uv_dest].uv = src[uv].uv
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.000065)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
    panels.free()
    return len(scars)


repaired_notches = patch_wing_notches(list(assembly_boundaries()))
source_coords = {name: [raw(v.co) for v in obj.data.vertices] for name, obj in source.items()}


def soften_rear(points):
    # Relax the restored rear panel into the neighboring original wales, using the same field on both cuts.
    rows = [(math.atan2(p.x, -p.z) * .34, p.y, math.hypot(p.x, p.z))
            for p in points if p.z < -.065 and .045 < p.y < .48]
    surface = KDTree(len(rows))
    for i, (angle, y, _) in enumerate(rows):
        surface.insert((angle, y, 0), i)
    surface.balance()

    def sample(p):
        x, y, z = p
        weight = (smooth(.065, .14, -z) * smooth(.14, .23, abs(x))
                  * smooth(.053, .115, y) * (1 - smooth(.40, .466, y)))
        if weight == 0:
            return p
        angle = math.atan2(x, -z) * .34
        neighbors = surface.find_range((angle, y, 0), .035)
        if len(neighbors) < 6:
            return p
        design = np.array([(rows[i][0]-angle, rows[i][1]-y, 1.) for _, i, _ in neighbors])
        radii = np.array([rows[i][2] for _, i, _ in neighbors])
        weights = np.array([math.exp(-(d / .022) ** 2) for _, _, d in neighbors])
        radius = float(np.linalg.lstsq(design * weights[:, None], radii * weights, rcond=None)[0][2])
        base = math.hypot(x, z)
        change = max(-.019, min(.019, (radius - base) * weight * .75))
        scale = 1 + change / base
        return Vector((x * scale, y, z * scale))

    return sample


relax_rear = soften_rear([p for points in source_coords.values() for p in points])
relaxed = {name: [relax_rear(p) for p in points] for name, points in source_coords.items()}


class Fit:
    def __init__(self, pose):
        self.pose = pose
        transforms, active = transforms_for(pose)
        self.hood = transforms[SOURCE['anchors']['Hood']]
        self.bodice = transforms[SOURCE['anchors']['Bodice']]
        self.world_to_hood = self.hood.inverted()
        self.hood_scale = self.hood.to_scale().x
        self.stock = []
        self.colliders = []
        self.eyes = {}
        eye_poses = {name: verts for name, verts, _ in local(pose, 'Hood', EYES)}
        for name, verts in eye_poses.items():
            extents = [(min(v[k] for v in verts), max(v[k] for v in verts)) for k in range(3)]
            self.eyes[name] = Vector([(a + b) * .5 for a, b in extents])
        self.eye_y = sum(v.y for v in self.eyes.values()) / len(EYES)
        self.eye_x = sum(abs(v.x) for v in self.eyes.values()) / len(EYES)
        self.eye_radius = min(
            max(v[k] for v in verts) - self.eyes[name][k]
            for name, verts in eye_poses.items() for k in range(2)
        ) - .0015
        self.eye_scale = self.eye_radius / SOURCE_RADIUS
        self.y_knots = [(SEAM, seam_height), (.435, -.022),
                        (SOURCE_EYE_Y - SOURCE_RADIUS, self.eye_y - self.eye_radius),
                        (SOURCE_EYE_Y + SOURCE_RADIUS, self.eye_y + self.eye_radius),
                        (.658, .333), (.7144, .392)]
        self.eye_trees = []
        for mesh in SOURCE['meshes']:
            if not active[mesh['node']]:
                continue
            tr = transforms[mesh['node']]
            verts = [tr @ Vector(v) for v in mesh['verts']]
            self.stock.append((mesh, verts, tr))
            if mesh['name'] in HEAD + TORSO:
                self.colliders.append(tree(verts, mesh['triangles']))
            if mesh['name'] in EYES:
                self.eye_trees.append(tree(verts, mesh['triangles']))
        self.ground = min(v.y for mesh, verts, _ in self.stock if mesh['name'].startswith('player_leg_')
                          for v in verts)
        self.seam_y = (self.hood @ Vector((0, seam_height, 0))).y
        self.bodice_bottom = (self.bodice @ Vector((0, -.159 if pose == 'Stand' else -.061, 0))).y

    def position(self, point):
        x, y, z = point
        relative = math.hypot(x, z)
        front = z / max(relative, .0001)
        base_x = x * .738
        base_z = z * .818
        eye_distance = math.hypot(abs(x) - SOURCE_EYE_X, y - SOURCE_EYE_Y)
        is_hood = y > SEAM + .000002
        if is_hood:
            hood_y = interpolate(self.y_knots, y)
            abs_x = abs(x)
            eye_x = interpolate([(0, 0), (.015, self.eye_x - self.eye_radius),
                                 (.155, self.eye_x + self.eye_radius), (.230, .268), (.362, .335)], abs_x)
            eye_band = smooth(SEAM, .452, y) * (1 - smooth(.599, .681, y))
            face_band = smooth(.05, .57, front)
            x_factor = eye_band * face_band
            depth_scale = interpolate([(SEAM, .818), (.445, 1.04), (.56, 1.12),
                                       (.660, .99), (.7144, .80)], y)
            base_x = mix(base_x, math.copysign(eye_x, x), x_factor)
            base_z = z * depth_scale - .008 * smooth(SEAM, .45, y)
            target_y = (self.hood @ Vector((0, hood_y, 0))).y
        else:
            bottom = min(1, max(0, (SEAM - y) / .431))
            base_x = x * mix(.738, .630, smooth(0., .48, bottom))
            base_z = z * mix(.818, .759, smooth(.10, .72, bottom))
            target_y = mix(self.seam_y, self.bodice_bottom, bottom)

        base_x *= self.hood_scale
        base_z *= self.hood_scale
        center_z = -.008 * self.hood_scale
        direction = Vector((base_x, 0, base_z - center_z))
        radius = direction.length
        if radius < .0001:
            direction = Vector((0, 0, 1))
        else:
            direction /= radius
        pivot = Vector((0, target_y, center_z))
        radial_hit = closest_hit(self.colliders, pivot + direction, -direction, 1.02)
        face_start = Vector((base_x, target_y, 1))
        facing = Vector((0, 0, -1))
        face_hit = closest_hit(self.colliders, face_start, facing, 1.01)
        clearance = self.hood_scale * (.017 if is_hood else .014)
        radial_clearance = clearance + self.hood_scale * (
            .013 + .007 * smooth(.585, .66, y)) * (1 - smooth(-.15, .56, front))
        radial_support = (radial_hit - pivot).dot(direction) if radial_hit is not None else 0.
        if front < .55:
            # Bridge the fine split between the stock head halves and catch facets between vertices.
            for dy in (-.019, -.009, .009, .019):
                sample = pivot + Vector((0, dy * self.hood_scale, 0))
                hit = closest_hit(self.colliders, sample + direction, -direction, 1.02)
                if hit is not None:
                    radial_support = max(radial_support, (hit - sample).dot(direction) - abs(dy) * .38)

        radial = pivot + direction * soften_max(radius, radial_support + radial_clearance, .025)
        face_z = soften_max(base_z, face_hit.z + clearance, .028) if face_hit is not None else base_z
        face = Vector((base_x, target_y, face_z))
        if is_hood and front > .54 and abs(eye_distance - SOURCE_RADIUS) < .041:
            aperture = 1 - smooth(.004, .041, abs(eye_distance - SOURCE_RADIUS))
            eye_hit = closest_hit(self.eye_trees, face_start, facing, 1)
            if eye_hit is not None:
                at_rim = eye_hit.z + .005 * self.hood_scale
                if face_hit is not None:
                    at_rim = soften_max(at_rim, face_hit.z + clearance, .016)
                face.z = mix(face.z, at_rim, aperture)

        blend = smooth(.19, .57, front)
        # At the contour of the stock head and torso, preserve the radial clearance.
        blend *= max(1 - smooth(.012, .065, (face - radial).length),
                     1 - smooth(.001, .029, abs(eye_distance - SOURCE_RADIUS)) if is_hood else 0.)
        result = radial.lerp(face, blend)
        return result


fits = {pose: Fit(pose) for pose in POSES}
fitted = {}
stock = {}
stage_objects = []


def add_mesh(name, vertices, faces, normals, mat, collection):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    for p in mesh.polygons:
        p.use_smooth = True
    if normals:
        mesh.normals_split_custom_set_from_vertices(normals)
    mesh.materials.append(mat)
    return obj


def collection(name):
    out = bpy.data.collections.new(name)
    scene.collection.children.link(out)
    return out


for pose, fit in fits.items():
    garment = collection(pose + ' • fitted cuts')
    fitted[pose] = {}
    for name in PARTS:
        obj = source[name].copy()
        obj.data = source[name].data.copy()
        obj.name = name + ' • ' + pose
        garment.objects.link(obj)
        for v, p in zip(obj.data.vertices, relaxed[name]):
            v.co = stage(fit.position(p) - Vector((0, fit.ground, 0)))
        obj.data.update()
        obj['asset_source'] = 'Boobees Valuables / Cast-Iron Boo-Bee / cleaned cut r2'
        obj['native_clip'] = 'PlayerAvatar - ' + pose + ' at 1.0 s'
        fitted[pose][name] = obj

    if args.draft:
        print(pose, 'eye centers', {k: list(v) for k, v in fit.eyes.items()},
              'radius', fit.eye_radius, 'seam y', fit.seam_y, flush=True)

for obj in list(scene.objects):
    if not any(obj == item for parts in fitted.values() for item in parts.values()):
        bpy.data.objects.remove(obj, do_unlink=True)


def triangulate_mesh(obj, ground):
    mesh = obj.data
    mesh.calc_loop_triangles()
    verts = [raw(v.co) + Vector((0, ground, 0)) for v in mesh.vertices]
    return tree(verts, [t.vertices[:] for t in mesh.loop_triangles])


def audit_pose(fit, parts):
    fronts = Vector((0, 0, -1))
    hood_bvh = triangulate_mesh(parts['Hood'], fit.ground)
    garments = [hood_bvh, triangulate_mesh(parts['Bodice'], fit.ground)]
    eye_discs = []
    ring_metrics = {}
    for name, center in fit.eyes.items():
        side = math.copysign(1., center.x)
        brim = [raw(v.co) + Vector((0, fit.ground, 0))
                for v, src in zip(parts['Hood'].data.vertices, source_coords['Hood'])
                if src.z > .14 and abs(math.hypot(src.x - side * SOURCE_EYE_X, src.y - SOURCE_EYE_Y)
                                       - SOURCE_RADIUS) < .000085]
        local_points = [fit.world_to_hood @ v for v in brim]
        brim_center = Vector(tuple((min(v[i] for v in local_points) + max(v[i] for v in local_points)) * .5
                                   for i in range(3)))
        center_error = (brim_center.xy - center.xy).length
        radius_error = max(abs((p.xy - center.xy).length - fit.eye_radius) for p in local_points)
        assert center_error < .00025 and radius_error < .0002, (fit.pose, name, center_error, radius_error)
        brim.sort(key=lambda p: math.atan2((fit.world_to_hood @ p).y - center.y,
                                          (fit.world_to_hood @ p).x - center.x))
        eye_discs.append(tree(brim + [fit.hood @ brim_center],
                              [(len(brim), i, (i+1) % len(brim)) for i in range(len(brim))]))
        ring_metrics[name] = {'centerXYInHoodAnchor': list(brim_center.xy),
                              'radius': fit.eye_radius, 'centerError': center_error,
                              'maxRimRadiusError': radius_error, 'rimVertices': len(brim)}
    head = [(m, v) for m, v, _ in fit.stock if m['name'] in HEAD]
    head_trees = [tree(v, m['triangles']) for m, v in head]
    floor, ceiling = (measure(p.y for _, v in head for p in v) for measure in (min, max))
    exposed = []
    head_rays = 0
    for k in range(1, 160):
        y = mix(floor, ceiling, k / 160)
        pivot = Vector((0, y, -.008 * fit.hood_scale))
        for a in range(150):
            rad = a * math.tau / 150
            direction = Vector((math.sin(rad), 0, math.cos(rad)))
            start = pivot + direction
            native = closest_hit(head_trees, start, -direction, 1.08)
            if native is None:
                continue
            coord = fit.world_to_hood @ native
            depth = (start - native).length
            inside_apertures = (closest_hit(eye_discs, start, -direction, depth) is not None
                                or closest_hit(fit.eye_trees, start, -direction, depth) is not None)
            if inside_apertures:
                continue
            head_rays += 1
            cloth = closest_hit(garments, start, -direction, 1.0)
            if cloth is None or (native - cloth).dot(direction) > .0005:
                exposed.append((round(math.degrees(rad), 2), tuple(round(v, 5) for v in coord)))

    eye_rays = 0
    for center in fit.eyes.values():
        for fraction in (0, .35, .70, .94, .98):
            for i in range(72):
                angle = i * math.tau / 72
                offset = fraction * fit.eye_radius * Vector((math.cos(angle), math.sin(angle), 0))
                p = fit.hood @ (center + offset)
                p.z = 1
                front_eye = closest_hit(fit.eye_trees, p, fronts, .93)
                if front_eye is None:
                    continue
                cloth = closest_hit([hood_bvh], p, fronts, (p - front_eye).length + .0002)
                assert cloth is None, (fit.pose, 'eye occluded', tuple(fit.world_to_hood @ p), fraction)
                eye_rays += 1

    source_seam = {name: [v.index for v, p in zip(parts[name].data.vertices, source_coords[name])
                          if abs(p.y - SEAM) <= .000015] for name in PARTS}
    sets = [[parts[name].data.vertices[i].co for i in source_seam[name]] for name in PARTS]
    index = KDTree(len(sets[1]))
    for i, v in enumerate(sets[1]):
        index.insert(v, i)
    index.balance()
    deltas = [index.find(v)[2] for v in sets[0]]
    coincident = [d for d in deltas if d < .0002]
    print('CHECK', fit.pose, 'head rays', head_rays, 'exposed', len(exposed), 'sample', exposed[::max(1, len(exposed)//16)],
          'eye rays', eye_rays, 'seam', len(coincident), len(sets[0]), len(sets[1]),
          'max error', max(coincident), 'nearest unmatched', [round(d, 5) for d in deltas if d >= .0002], flush=True)
    return {'headRaysOutsideEyeApertures': head_rays, 'uncoveredHeadRays': len(exposed),
            'unoccludedEyeRays': eye_rays, 'sharedSeamVertices': len(coincident),
            'hoodSeamVertices': len(sets[0]), 'bodiceSeamVertices': len(sets[1]),
            'maxSharedSeamError': max(coincident), 'eyeApertures': ring_metrics}


checks = {pose: audit_pose(fit, fitted[pose]) for pose, fit in fits.items()}


def aim(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()


for pose, fit in fits.items():
    mocap = collection(pose + ' • native Semibot for preview')
    stock[pose] = []
    for mesh, verts, tr in fit.stock:
        locations = [stage(v - Vector((0, fit.ground, 0))) for v in verts]
        inv = tr.to_3x3().inverted_safe().transposed()
        normals = [stage((inv @ Vector(v[:3])).normalized()) for v in mesh['normals']]
        obj = add_mesh(mesh['name'], locations, mesh['triangles'], normals, stock_material(mesh['name']), mocap)
        stock[pose].append(obj)

bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -.013))
floor = bpy.context.object
floor.data.materials.append(material('Slate floor', (56, 65, 72), .83))
stage_objects.append(floor)
for position, power, size, color in (
        ((-3.0, -4.0, 5), 625, 4, (1, .91, .79)),
        ((3.0, -3.0, 2.6), 380, 3.1, (.75, .86, 1)),
        ((1.0, 3.0, 4.2), 650, 2.55, (1, .88, .73))):
    bpy.ops.object.light_add(type='AREA', location=position)
    light = bpy.context.object
    light.data.energy = power
    light.data.shape = 'DISK'
    light.data.size = size
    light.data.color = color
    aim(light, (0, 0, .85))
    stage_objects.append(light)
scene.world = bpy.data.worlds.new('Studio')
scene.world.color = (.13, .13, .13)
bpy.ops.object.camera_add()
camera = bpy.context.object
camera.data.type = 'ORTHO'
scene.camera = camera
stage_objects.append(camera)
scene.cycles.samples = 8 if args.draft else 28
scene.cycles.use_denoising = True
scene.view_settings.view_transform = 'AgX'
scene.render.resolution_x = 580 if args.draft else 900
scene.render.resolution_y = 650 if args.draft else 1010
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'

view_positions = {}
for pose in POSES:
    objects = {p: [*fitted[p].values(), *stock[p]] for p in POSES}
    for name, group in objects.items():
        for obj in group:
            obj.hide_render = name != pose
    views = [('front', 0), ('three-quarter', 38), ('rear', 155)]
    for name, angle in views:
        height = .86
        rad = math.radians(angle)
        camera.location = (5 * math.sin(rad), -5 * math.cos(rad), height + .62)
        camera.data.ortho_scale = 1.94
        aim(camera, (0, 0, height))
        bpy.context.view_layer.update()
        fit = fits[pose]
        seam = min((p for p in relaxed['Hood'] if abs(p.y - SEAM) < .00001),
                   key=lambda p: (p.x - .145) ** 2 + (p.z - .320) ** 2)
        world = stage(fit.position(seam) - Vector((0, fit.ground, 0)))
        uv = world_to_camera_view(scene, camera, world)
        view_positions[f'{pose.lower()}-{name}'] = [
            round(uv.x * scene.render.resolution_x), round((1 - uv.y) * scene.render.resolution_y)]
        scene.render.filepath = str(output / (pose.lower() + '-' + name + '.png'))
        bpy.ops.render.render(write_still=True)

if not args.draft:
    for pose, fit in fits.items():
        for name, obj in fitted[pose].items():
            matrix = fit.hood if name == 'Hood' else fit.bodice
            origin = stage(matrix.translation - Vector((0, fit.ground, 0)))
            scale = matrix.to_scale()
            obj.location = origin
            obj.scale = (scale.x, scale.z, scale.y)
            for v in obj.data.vertices:
                offset = v.co - origin
                v.co = Vector((offset.x / scale.x, offset.y / scale.z, offset.z / scale.y))
            obj.data.update()
            obj['mount'] = 'HeadTop' if name == 'Hood' else 'BodyTop'
            obj.hide_render = False
    receipt = {
        'source': 'Boobees Valuables 0.2.15 / cleaned Cast-Iron Boo-Bee r2',
        'avatar': 'Semibot / R.E.P.O. 0.5.3 / build 26813769',
        'clipSampleSeconds': 1.0,
        'units': 'Unity units in the indicated local anchor, before crouch scale',
        'wingNotchesRepaired': repaired_notches,
        'runtimeIntegration': False,
        'poses': checks,
        'seamMarkerPixels': view_positions,
        'trianglesPerPose': {name: len(obj.data.polygons) for name, obj in fitted['Stand'].items()},
    }
    (output / 'fit-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    for obj in [*stage_objects, *stock['Stand'], *stock['Crouch']]:
        bpy.data.objects.remove(obj, do_unlink=True)
    for col in list(scene.collection.children):
        if not col.objects and not col.children:
            bpy.data.collections.remove(col)
    crouched = bpy.data.collections['Crouch • fitted cuts']
    crouched.hide_viewport = True
    crouched.hide_render = True
    bpy.data.orphans_purge(do_recursive=True)
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'Semibot-hood-bodice-fit.blend'))
