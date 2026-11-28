"""Fit the full Boo-Bee outfit around the approved hood and bodice pose meshes."""

import argparse
import bisect
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.local' / 'semibot-preview'))
from measure_fit import SOURCE, local, transforms_for

dist = ROOT / 'dist'
cuts = dist / 'cast-iron-boo-clean' / 'Cast-Iron-Boo-Bee-cut.blend'
garments = dist / 'cast-iron-boo-cut' / 'meshy-garments' / 'Meshy-garments.blend'
base = dist / 'semibot-hood-fit' / 'Semibot-hood-bodice-fit.blend'
poses = ('Stand', 'Crouch')

# Unity coordinates from the installed game, in Blender's stage basis.
BASIS = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))


def stage(v):
    return Vector((v.x, -v.z, v.y))


def unity(v):
    return Vector((v.x, v.z, -v.y))


def mix(a, b, t):
    return a + (b - a) * t


def smooth(a, b, x):
    t = min(1., max(0., (x - a) / (b - a)))
    return t * t * (3. - 2. * t)


def lerp_rows(rows, x):
    i = max(0, min(bisect.bisect_right(rows, (x, math.inf)) - 1, len(rows) - 2))
    xa, a = rows[i]
    xb, b = rows[i + 1]
    return mix(a, b, (x - xa) / (xb - xa))


def bvh(mesh, coordinates):
    mesh.calc_loop_triangles()
    return BVHTree.FromPolygons(coordinates, [face.vertices[:] for face in mesh.loop_triangles],
                               all_triangles=True)


def mesh_bounds(points):
    return [[round(extreme(p[i] for p in points), 6) for i in range(3)] for extreme in (min, max)]


def append_assets(path, names):
    with bpy.data.libraries.load(str(path), link=False) as (source, destination):
        assert set(names) <= set(source.objects), (path, names)
        destination.objects = list(names)
    return dict(zip(names, destination.objects))


def material(name, rgba, roughness):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = rgba
    mat.use_nodes = True
    shader = mat.node_tree.nodes['Principled BSDF']
    shader.inputs['Base Color'].default_value = rgba
    shader.inputs['Roughness'].default_value = roughness
    return mat


def fabric_patches(hood, region, radius):
    atlas = next(n.image for n in hood.data.materials[0].node_tree.nodes
                 if n.type == 'TEX_IMAGE' and n.image.name.startswith('color.png'))
    width, height = atlas.size
    pixels = np.asarray(atlas.pixels[:], dtype=np.float32).reshape(height, width, 4)
    uv = hood.data.uv_layers.active
    for face in hood.data.polygons:
        if not region(face.center):
            continue
        c = sum((uv.data[i].uv for i in face.loop_indices), Vector((0, 0))) / len(face.loop_indices)
        x, y = round(c.x * width), round(c.y * height)
        patch = pixels[y - radius:y + radius, x - radius:x + radius, :3]
        if patch.size and patch.sum(axis=2).min() > 1.15:
            yield patch


def sample_ivory(hood):
    patches = fabric_patches(hood, lambda p: .21 < p.z < .315 and .07 < p.x < .16, 8)
    color = min(patches, key=lambda patch: patch.std(axis=(0, 1)).sum()).mean(axis=(0, 1))
    return (*[float(v) for v in color], 1)


def shoulder_ivory(hood):
    patches = fabric_patches(hood, lambda p: .215 < abs(p.x) < .30 and -.219 < p.z < -.07
                             and -.38 < p.y < -.16, 4)
    colors = [np.median(patch, axis=(0, 1)) for patch in patches]
    assert colors, 'Shoulder fabric sample missing'
    srgb = np.median(colors, axis=0)
    # Byte-image samples are encoded in sRGB. Values plugged into Base Color are scene-linear.
    linear = ((srgb + .055) / 1.055) ** 2.4
    return (*[float(v) for v in linear], 1.)


def cloth_material(name, ivory, striped=False, sheen=.23, roughness=.78):
    mat = material(name, ivory, roughness)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes['Principled BSDF']
    tex = nodes.new('ShaderNodeTexCoord')
    shader.inputs['Sheen Weight'].default_value = sheen
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 245.
    noise.inputs['Detail'].default_value = 2.
    links.new(tex.outputs['Object'], noise.inputs['Vector'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .17
    bump.inputs['Distance'].default_value = .0035
    links.new(noise.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], shader.inputs['Normal'])
    if striped:
        xyz = nodes.new('ShaderNodeSeparateXYZ')
        links.new(tex.outputs['Generated'], xyz.inputs['Vector'])
        ramp = nodes.new('ShaderNodeValToRGB')
        links.new(xyz.outputs['Z'], ramp.inputs['Fac'])
        ramp.color_ramp.interpolation = 'CONSTANT'
        charcoal = (.065, .046, .034, 1)
        honey = (.73, .40, .09, 1)
        layers = [(0, charcoal), (.24, honey), (.43, charcoal), (.58, honey), (.76, charcoal), (.87, ivory)]
        for i, (height, color) in enumerate(layers):
            ramp_element = ramp.color_ramp.elements[i] if i < 2 else ramp.color_ramp.elements.new(height)
            ramp_element.position, ramp_element.color = height, color
        links.new(ramp.outputs['Color'], shader.inputs['Base Color'])
    return mat


def copy_mesh(asset, name, destination):
    obj = asset.copy()
    obj.data = asset.data.copy()
    obj.name = name
    destination.objects.link(obj)
    return obj


def set_mesh_world(obj, positions, mount):
    inverse = mount.inverted()
    for vertex, p in zip(obj.data.vertices, positions):
        vertex.co = inverse @ p
    obj.matrix_world = mount
    obj.data.update()


def prepare_limb(obj, kind, side, fabric):
    # Widen the Meshy shell modestly and follow the native taper at the wrist and toe.
    obj.data.materials.clear()
    obj.data.materials.append(fabric)
    for face in obj.data.polygons:
        face.material_index = 0
        face.use_smooth = True
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.000015)
    for vert in bm.verts:
        x, y, z = vert.co
        if kind == 'Sleeve':
            u = side * x
            target = mix(u, u * 1.249, smooth(-.02, .05, u))
            radial_scale = mix(1.16, .82, smooth(.1, .48, target))
            vert.co = (side * target, y * radial_scale, z * radial_scale)
        else:
            height = mix(-.565, -.181, (z + .55) / .62)
            radial_scale = mix(.66, .86, smooth(-.57, -.32, height))
            vert.co = (x * radial_scale, y * radial_scale, height)
    if kind == 'Sleeve':
        tip = [edge for edge in bm.edges if edge.is_boundary and all(side * v.co.x > .47 for v in edge.verts)]
        cap = bmesh.ops.holes_fill(bm, edges=tip, sides=0)
        for face in cap['faces']:
            face.smooth = True
        bmesh.ops.triangulate(bm, faces=cap['faces'])
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def stock_color(name):
    if name.startswith('player_iris'):
        return (.031, .038, .051, 1)
    if name.startswith('player_eye'):
        return (.82, .85, .85, 1)
    if name == 'player_health_LED':
        return (.05, .04, .031, 1)
    if name.startswith(('player_arm', 'player_leg', 'player_head_bot', 'player_health_frame')):
        return (.16, .21, .26, 1)
    return (.25, .32, .35, 1)


def add_stock(collection, transforms, visible, ground):
    objects = {}
    for row in SOURCE['meshes']:
        if not visible[row['node']]:
            continue
        name, tr = row['name'], transforms[row['node']]
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([stage(tr @ Vector(p)) - Vector((0, 0, ground)) for p in row['verts']],
                        [], row['triangles'])
        mesh.update()
        for p in mesh.polygons:
            p.use_smooth = True
        if row['normals']:
            inv = tr.to_3x3().inverted_safe().transposed()
            mesh.normals_split_custom_set_from_vertices(
                [stage((inv @ Vector(n[:3])).normalized()) for n in row['normals']])
        mesh.materials.append(material('Preview ' + name, stock_color(name), .47))
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        objects[obj.name] = obj
    return objects


def ring_at_bodice_edge(bodice):
    surface = [bodice.matrix_world @ v.co for v in bodice.data.vertices]
    bottom = min(p.z for p in surface)
    by_angle = {}
    for p in surface:
        if abs(p.z - bottom) > .00013:
            continue
        angle = round(math.atan2(p.x, -p.y), 5)
        radial = math.hypot(p.x, p.y)
        by_angle[angle] = max(radial, by_angle.get(angle, 0))
    values = sorted(by_angle.items())
    assert len(values) > 100
    x, a = values[-1]
    y, b = values[0]
    return bottom, [(x - math.tau, a), *values, (y + math.tau, b)]


def shape_bodice(bodice, stock):
    mount = bodice.matrix_world.copy()
    points = [mount @ v.co for v in bodice.data.vertices]
    lo, hi = (f(p.z for p in points) for f in (min, max))
    old = bvh(bodice.data, points)
    torso = [bvh(o.data, [v.co for v in o.data.vertices]) for name, o in stock.items()
             if name.startswith(('player_body_', 'player_health_', 'player_head_bot'))]
    positions = []
    forward = Vector((0, 1, 0))
    for p in points:
        x, y, z = p
        t = (z - lo) / (hi - lo)
        side = abs(x)
        front = smooth(.15, .28, -y) * (1 - smooth(.205, .274, side))
        interior = smooth(.075, .32, t) * (1 - smooth(.785, .966, t))
        mask = front * interior
        if mask < .00001:
            positions.append(p)
            continue
        center = .113
        drop = .145 * math.exp(-((side - center) / .133) ** 4) * mask
        width = 1 + .09 * math.exp(-((t - .47) / .19) ** 2) - .30 * smooth(.48, .82, t)
        x += math.copysign(1., x) * (side - center) * (width - 1) * mask * smooth(0, .053, side)
        z -= (hi - lo) * drop
        center_recess = .021 * math.exp(-(side / .054) ** 2 - ((t - .58) / .265) ** 2)
        lower_fullness = .019 * math.exp(-((side - center) / .087) ** 2 - ((t - .54) / .225) ** 2)
        upper_taper = .017 * smooth(.64, .86, t)
        y += mask * (center_recess + upper_taper - lower_fullness)
        probe = Vector((x, -1, z))
        for surface in torso:
            hit = surface.ray_cast(probe, forward, 1.)[0]
            if hit is not None:
                y = min(y, hit.y - .011)
        positions.append(Vector((x, y, z)))

    seam_drift = max((a - b).length for a, b in zip(points, positions)
                     if abs(a.z - lo) < .0001 or abs(a.z - hi) < .0001)
    assert seam_drift < .000001
    updated = bvh(bodice.data, positions)

    def peak(surface):
        candidates = []
        for i in range(29):
            t = .20 + .65 * i / 28
            for x in (.085, .10, .115, .13, .145, .16, .175):
                sample = surface.ray_cast(Vector((x, -1, mix(lo, hi, t))), forward, 1.)[0]
                if sample is not None:
                    candidates.append((-sample.y, t))
        return max(candidates)

    before, after = peak(old), peak(updated)
    assert after[1] < before[1] - .07, (before, after)
    tested, exposed = 0, 0
    for row in range(1, 69):
        for col in range(75):
            start = Vector((mix(-.274, .274, col / 74), -1, mix(lo, hi, row / 69)))
            skin = [hit.y for surface in torso if (hit := surface.ray_cast(start, forward, 1.)[0]) is not None]
            if not skin:
                continue
            native_depth = min(skin)
            baseline = old.ray_cast(start, forward, 1.)[0]
            if baseline is None or baseline.y > native_depth + .0005:
                continue
            tested += 1
            cloth = updated.ray_cast(start, forward, 1.)[0]
            if cloth is None or cloth.y > native_depth + .0005:
                exposed += 1
    assert tested > 2500 and exposed == 0, (tested, exposed)
    set_mesh_world(bodice, positions, mount)
    return {'baselinePeak': before, 'currentPeak': after, 'seamDrift': seam_drift,
            'torsoRays': tested, 'newExposures': exposed}


def fit_hem(obj, bodice, stock, pose, torso_mount):
    edge_z, edge = ring_at_bodice_edge(bodice)
    stock_trees = [bvh(o.data, [v.co for v in o.data.vertices]) for name, o in stock.items()
                   if name.startswith(('player_body_', 'player_health_', 'player_leg_'))]
    src = [v.co.copy() for v in obj.data.vertices]
    # Top points ride just beneath the old bodice seam. The flare follows the cut's pleating.
    skirt_drop = .235 if pose == 'Stand' else .086
    world = []
    for point in src:
        x, y, z = point
        t = min(1., max(0., (-.08 - z) / .49))
        x_axis, depth_axis = .63 * x, -.759 * y
        angle = math.atan2(x_axis, depth_axis)
        radial = math.hypot(x_axis, depth_axis)
        seam = lerp_rows(edge, angle)
        fold = t ** 1.38 if pose == 'Crouch' else t
        height = edge_z + .007 - (skirt_drop + .007) * fold
        flare = mix(seam - .005, min(.433, radial * (.89 if pose == 'Stand' else .84)),
                    smooth(.01, .62, t))
        direction = Vector((math.sin(angle), -math.cos(angle), 0))
        center = Vector((0, 0, height))
        guard = 0.
        for candidate in stock_trees:
            hit, _, _, _ = candidate.ray_cast(center + direction, -direction, 1.)
            if hit is not None:
                guard = max(guard, (hit - center).dot(direction))
        flare = max(flare, guard + .012 * smooth(.06, .42, t))
        world.append(center + direction * flare)
    set_mesh_world(obj, world, torso_mount)
    obj['mount'] = 'BodyTop'
    return edge_z


def fit_antennae(obj, hood, head_mount):
    hood_bvh = bvh(hood.data, [hood.matrix_world @ v.co for v in hood.data.vertices])
    raw = [v.co.copy() for v in obj.data.vertices]
    roots = {}
    for side in (-1, 1):
        stem = [p for p in raw if side * p.x > 0]
        low = min(p.z for p in stem)
        root = [p for p in stem if p.z < low + .026]
        tip = head_mount @ Vector((side * .104, -.291, .55))
        hit, _, _, _ = hood_bvh.ray_cast(tip, Vector((0, 0, -1)), .40)
        assert hit is not None
        roots[side] = (sum(root, Vector()) / len(root),
                       head_mount.inverted() @ (hit - Vector((0, 0, .012))))
    points = []
    for p in raw:
        source, dest = roots[1 if p.x > 0 else -1]
        delta = p - source
        points.append(dest + Vector((delta.x * .84, delta.y * .84, delta.z * .89)))
    for v, p in zip(obj.data.vertices, points):
        v.co = p
    obj.matrix_world = head_mount
    obj.data.update()
    obj['mount'] = 'HeadTop'


def fit_wings(obj, torso_mount, edge_z, pose):
    scale = .95 if pose == 'Crouch' else 1.
    # Keep the pair rigid while lowering it with the torso in the crouch frame.
    neutral_height = edge_z + (.249 if pose == 'Stand' else .155)
    positions = [Vector((v.co.x * .82 * scale, (v.co.y * .76 + .083) * scale,
                         neutral_height + (v.co.z - .315) * .80 * scale)) for v in obj.data.vertices]
    set_mesh_world(obj, positions, torso_mount)
    obj['mount'] = 'BodyTop'


def limb_check(garment, pose, kind, side_name, stock_name):
    _, positions, faces = local(pose, side_name + ' ' + kind, [stock_name])[0]
    stock_tree = BVHTree.FromPolygons(positions, faces, all_triangles=True)
    cloth = bvh(garment.data, [unity(v.co) for v in garment.data.vertices])
    axis = 0 if kind == 'Sleeve' else 1
    side = 1 if side_name == 'Right' else -1
    rows = [(i * .532 * side / 67) for i in range(68)] if axis == 0 else [
        mix(-.547, -.188, i / 67) for i in range(68)]
    tested, misses, depth = 0, 0, 0.
    for h in rows:
        for i in range(36):
            angle = i * math.tau / 36
            u, v = math.cos(angle), math.sin(angle)
            start = Vector((h, u, v) if axis == 0 else (u, h, v))
            direction = Vector((0, -u, -v) if axis == 0 else (-u, 0, -v))
            hit, _, _, stock_depth = stock_tree.ray_cast(start, direction, 1.)
            if hit is None:
                continue
            tested += 1
            shell, _, _, shell_depth = cloth.ray_cast(start, direction, 1.)
            if shell is None or stock_depth < shell_depth - .0007:
                misses += 1
                depth = max(depth, .1 if shell is None else shell_depth - stock_depth)
    return dict(tested=tested, exposed=misses, maxPenetration=round(depth, 5))


def collection(name):
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def build_pose(pose, cut_assets, limb_assets, sleeve_fabric, sock_fabric):
    scene = bpy.context.scene
    outfit = bpy.data.collections[pose + ' • fitted cuts']
    outfit.hide_viewport = False
    outfit.hide_render = False
    hood = bpy.data.objects['Hood • ' + pose]
    bodice = bpy.data.objects['Bodice • ' + pose]
    transforms, visible = transforms_for(pose)
    ground = min((transforms[row['node']] @ Vector(p)).y for row in SOURCE['meshes']
                 if visible[row['node']] and row['name'].startswith('player_leg_') for p in row['verts'])
    ground_shift = Matrix.Translation((0, 0, -ground))

    def mounting(anchor):
        return ground_shift @ BASIS @ transforms[SOURCE['anchors'][anchor]] @ BASIS.inverted()

    stock = add_stock(collection(pose + ' • preview avatar'), transforms, visible, ground)
    pieces = {'Hood': hood, 'Bodice': bodice}
    for part in ('Hem', 'Antennae', 'Wings'):
        pieces[part] = copy_mesh(cut_assets[part], part + ' • ' + pose, outfit)
        pieces[part]['asset_source'] = 'Boobees Valuables / Cast-Iron Boo-Bee cut'
    bpy.context.view_layer.update()
    torso, head = mounting('Bodice'), mounting('Hood')
    chest_fit = shape_bodice(bodice, stock)
    edge_z = fit_hem(pieces['Hem'], bodice, stock, pose, torso)
    fit_antennae(pieces['Antennae'], hood, head)
    fit_wings(pieces['Wings'], torso, edge_z, pose)
    fit_checks = {'bodice': chest_fit}
    for side, marker in (('Left', 'L'), ('Right', 'R')):
        for kind, native, fabric in (('Sleeve', 'arm', sleeve_fabric), ('Sock', 'leg', sock_fabric)):
            part = side + ' ' + kind
            asset_name = side.lower() + '-' + kind.lower()
            obj = copy_mesh(limb_assets[asset_name], part + ' • ' + pose, outfit)
            obj.matrix_world = mounting(part)
            prepare_limb(obj, kind, -1 if side == 'Left' else 1, fabric)
            obj['mount'] = ('Arm' if kind == 'Sleeve' else 'Leg') + marker
            obj['asset_source'] = 'Meshy candidate fitted over the stock limb cross-section'
            pieces[part] = obj
            fit_checks[part] = limb_check(obj, pose, kind, side, 'player_' + native + '_' + marker)
    scene.view_layers[0].update()
    sole = min((pieces[part].matrix_world @ v.co).z
               for part in ('Left Sock', 'Right Sock') for v in pieces[part].data.vertices)
    if sole < 0:
        for obj in [*pieces.values(), *stock.values()]:
            obj.location.z -= sole
    scene.view_layers[0].update()
    fit_checks['waistHeight'] = round(edge_z - min(0, sole), 6)
    fit_checks['stockBodyBottomVisible'] = visible[SOURCE['anchors']['Mantle']]
    fit_checks['pieces'] = len(pieces)
    assert len(pieces) == 9
    assert all(check['exposed'] == 0 for name, check in fit_checks.items()
               if name.endswith(('Sleeve', 'Sock'))), (pose, fit_checks)
    for name, obj in pieces.items():
        obj.data.calc_loop_triangles()
        obj['pose'] = pose
        fit_checks.setdefault('triangles', {})[name] = len(obj.data.loop_triangles)
        fit_checks.setdefault('stageBounds', {})[name] = mesh_bounds([obj.matrix_world @ v.co for v in obj.data.vertices])
    print('FIT', pose, json.dumps(fit_checks), flush=True)
    return pieces, stock, fit_checks


def point_camera(camera, target):
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat('-Z', 'Y').to_euler()


def setup_stage(draft=False):
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -.009))
    floor = bpy.context.object
    floor.data.materials.append(material('Slate stage', (.045, .060, .074, 1), .84))
    stage_objects = [floor]
    for pos, power, size, color in (
            ((-3, -4, 5), 620, 4, (1, .93, .83)),
            ((3, -3, 3.3), 380, 3.1, (.76, .86, 1)),
            ((1, 3, 4.4), 630, 2.8, (1, .87, .71))):
        bpy.ops.object.light_add(type='AREA', location=pos)
        light = bpy.context.object
        light.data.energy = power
        light.data.shape = 'DISK'
        light.data.size = size
        light.data.color = color
        point_camera(light, (0, 0, .9))
        stage_objects.append(light)
    scene.world = bpy.data.worlds.new('Studio')
    scene.world.color = (.135, .135, .135)
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 2.20
    scene.camera = camera
    stage_objects.append(camera)
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 8 if draft else 28
    scene.cycles.use_denoising = True
    scene.view_settings.view_transform = 'AgX'
    scene.render.resolution_x = 570 if draft else 810
    scene.render.resolution_y = 700 if draft else 996
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    return camera, stage_objects


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--draft', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=str(base))
    cut_assets = append_assets(cuts, ['Antennae', 'Wings', 'Hem'])
    limb_assets = append_assets(garments, [f'{s}-{p}' for s in ('left', 'right') for p in ('sleeve', 'sock')])
    ivory = sample_ivory(bpy.data.objects['Hood • Stand'])
    shoulder = shoulder_ivory(bpy.data.objects['Hood • Stand'])
    sleeve_fabric = cloth_material('Boo-Bee shoulder ivory', shoulder, sheen=0., roughness=.74)
    sock_fabric = cloth_material('Boo-Bee sock knit', ivory, striped=True)
    prepared = {pose: build_pose(pose, cut_assets, limb_assets, sleeve_fabric, sock_fabric) for pose in poses}
    camera, stage_objects = setup_stage(args.draft)
    scene = bpy.context.scene
    views = [('front', 12), ('side', 49), ('back', 155)]
    for pose in prepared:
        for other, (pieces, stock, _) in prepared.items():
            for obj in [*pieces.values(), *stock.values()]:
                obj.hide_render = other != pose
        for view, angle in views:
            rad = math.radians(angle)
            camera.location = (5 * math.sin(rad), -5 * math.cos(rad), 1.55)
            point_camera(camera, (0, 0, .99))
            scene.render.filepath = str(output / f'{pose.lower()}-{view}.png')
            bpy.ops.render.render(write_still=True)
    receipt = dict(avatar='Semibot / R.E.P.O. 0.5.3 / build 26813769',
                   clipSampleSeconds=1.0, hoodAndBodiceInput=base.name,
                   verificationMethod='Baseline/candidate probes only; no Harness2 adapter execution',
                   runtimeIntegration=False, sleeveBaseLinearRGBA=shoulder,
                   poses={pose: p[2] for pose, p in prepared.items()})
    (output / 'fit-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    if args.draft:
        return
    for pose, (pieces, stock, _) in prepared.items():
        for obj in stock.values():
            bpy.data.objects.remove(obj, do_unlink=True)
        for obj in pieces.values():
            obj.hide_render = False
        bpy.data.collections.remove(bpy.data.collections[pose + ' • preview avatar'])
    for obj in stage_objects:
        bpy.data.objects.remove(obj, do_unlink=True)
    for obj in [*cut_assets.values(), *limb_assets.values()]:
        bpy.data.objects.remove(obj, do_unlink=True)
    crouch = bpy.data.collections['Crouch • fitted cuts']
    crouch.hide_viewport = True
    crouch.hide_render = True
    bpy.data.orphans_purge(do_recursive=True)
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'Boobees-full-outfit-fit.blend'))


if __name__ == '__main__':
    main()
