"""Split the original cloth at the native jaw line and fit both moving shells."""

import argparse
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_semibot_outfit import BASIS, SOURCE, bvh, dist, local, mix, poses, smooth, stage, transforms_for
from preview_semibot_mouth import DRIVER_NAME, MOUTH_STATES, below, jaw_delta

CUT_HEIGHT = -.006
CENTER = Vector((0, -.244, 0))
UPPER_MESH = ['player_head_top']
LOWER_MESH = ['player_head_bot_sphere', 'player_head_bot_flat']
SUPPORT_MESH = ['player_body_top_sphere', 'player_body_top_flat', 'player_health_frame']


def colliders(pose, labels):
    return [BVHTree.FromPolygons([stage(v) for v in points], faces, all_triangles=True)
            for _, points, faces in local(pose, 'Hood', labels)]


def radial_surface(trees, direction, height):
    origin = CENTER + Vector((0, 0, height))
    return max(((p - origin).dot(direction) for t in trees
                if (p := t.ray_cast(origin + direction, -direction, 1.0001)[0]) is not None),
               default=0.)


def supported_radius(trees, direction, height):
    # A neighboring ray covers narrow gaps between the original faceted shell's mesh sections.
    return max(radial_surface(trees, Matrix.Rotation(a, 3, 'Z') @ direction, height)
               for a in (-.022, 0., .022))


def eye_protection(point):
    front = CENTER.y - point.y
    radius = math.hypot(abs(point.x) - .12088, point.z - .11889)
    return smooth(.11, .166, front) * smooth(-.003, .012, point.z) * (1 - smooth(.106, .151, radius))


def fit_point(point, upper, native, lower_support):
    x, y, z = point
    d = Vector((x, y - CENTER.y, 0))
    r = d.length
    if r < .0001:
        return point.copy()
    d /= r
    rim = 1 - smooth(.000001, .038 if upper else .041, abs(z - CUT_HEIGHT))
    rear = smooth(-.060, .012, y)
    desired_height = mix(z, (-.004 + .009 * rear) if upper else (-.0114 - .002 * rear), rim)
    rim_radius = max(supported_radius(native[True], d, .005),
                     supported_radius(native[True], d, .011) - .003,
                     supported_radius(native[False], d, -.020)) + .010

    if upper:
        guard = radial_surface(native[True], d, desired_height)
        fit = .66 * (1 - smooth(.216, .325, z))
        clear = .012
        protection = eye_protection(point)
        if protection == 1:
            return point.copy()
    else:
        guard = supported_radius(lower_support, d, desired_height)
        fit = .73 * smooth(-.189, -.108, z)
        clear = .017
        protection = 0.
        if z <= -.188:
            return point.copy()

    # Keep relief from the original drape, while removing the loose lip that covered the jaw.
    target = mix(r, guard + clear, fit) if guard > .004 else r
    target = mix(target, rim_radius, rim)
    if guard > .004:
        target = max(target, guard + .0085)
    if not upper:
        # A little ease below the turned edge clears the lower shell's curved bevel.
        target += .006 * smooth(-.072, -.026, z) * (1 - smooth(-.017, -.007, z))
    target = mix(target, r, protection)
    return CENTER + d * target + Vector((0, 0, mix(desired_height, z, protection)))


def finish_edge(bm, borders, upper):
    if not borders:
        return 0
    turned = {}
    uv = bm.loops.layers.uv.active
    for edge in borders:
        outside = edge.link_loops[0]
        a, b = outside.vert, outside.link_loop_next.vert
        for v in (a, b):
            if v not in turned:
                direction = (v.co - CENTER).to_2d().normalized()
                turned[v] = bm.verts.new(v.co + Vector((-direction.x * .006, -direction.y * .006,
                                                        .002 if upper else -.002)))
        lip = bm.faces.new((b, a, turned[a], turned[b]))
        lip.material_index = outside.face.material_index
        lip.smooth = True
        for loop, donor in zip(lip.loops, (outside.link_loop_next, outside, outside, outside.link_loop_next)):
            loop[uv].uv = donor[uv].uv
    return len(borders)


def close_crown_pinholes(bm):
    edges = [edge for edge in bm.edges if edge.is_boundary and min(v.co.z for v in edge.verts) > .285]
    uv = bm.loops.layers.uv.active
    texels = {v: next(iter(v.link_loops))[uv].uv.copy() for edge in edges for v in edge.verts}
    filled = bmesh.ops.holes_fill(bm, edges=edges, sides=5)['faces']
    for face in filled:
        for loop in face.loops:
            loop[uv].uv = texels[loop.vert]
    return len(filled)


def section(source, upper, native, lower_support, destination):
    mesh = source.data.copy()
    if upper:
        obj = source
        obj.data = mesh
    else:
        obj = bpy.data.objects.new(source.name.replace('Hood •', 'Hood Lower •'), mesh)
        destination.objects.link(obj)
        obj.matrix_world = source.matrix_world.copy()
        for k, v in source.items():
            obj[k] = v

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.bisect_plane(bm, geom=[*bm.verts, *bm.edges, *bm.faces], dist=.000001,
                         plane_co=(0, 0, CUT_HEIGHT), plane_no=(0, 0, 1), use_snap_center=True,
                         clear_outer=not upper, clear_inner=upper)
    if upper:
        close_crown_pinholes(bm)
    else:
        # The low-resolution original spans the lower-jaw bevel with several long triangles.
        # Split them before conforming the cloth so their interior also clears the native surface.
        long_edges = [e for e in bm.edges if not e.is_boundary and e.calc_length() > .026
                      and max(v.co.z for v in e.verts) > -.175]
        bmesh.ops.subdivide_edges(bm, edges=long_edges, cuts=1, use_grid_fill=True)
    borders = [edge for edge in bm.edges if edge.is_boundary
               and all(abs(v.co.z - CUT_HEIGHT) < .000004 for v in edge.verts)]
    assert len(borders) > 50
    for v in bm.verts:
        v.co = fit_point(v.co, upper, native, lower_support)
    bound = finish_edge(bm, borders, upper)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    for face in bm.faces:
        face.smooth = True
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj['mount'] = 'HeadTop' if upper else 'HeadBottom'
    obj['jaw_edge'] = 'Turned cloth bound to the matching native jaw'
    return obj, bound


def check_shells(pose, upper, lower, bodice, mount, native, lower_support):
    # All three shells still use the same HeadTop coordinates at this point.
    trees = [bvh(obj.data, [v.co for v in obj.data.vertices]) for obj in (upper, lower)]
    torso = bvh(bodice.data, [mount.inverted() @ bodice.matrix_world @ v.co for v in bodice.data.vertices])
    eyes = colliders(pose, ['player_eye_L', 'player_eye_R'])
    covered, visible = 0, []
    for step in range(143):
        z = mix(-.362, .369, step / 142)
        if -.018 < z < .009:
            continue
        for a in range(144):
            angle = a * math.tau / 144
            direction = Vector((math.sin(angle), -math.cos(angle), 0))
            origin = CENTER + Vector((0, 0, z))
            start = origin + direction
            radius = radial_surface(lower_support if -.212 < z < -.018 else native[z > 0], direction, z)
            if not radius:
                continue
            skin = origin + direction * radius
            front_eye = any(t.ray_cast(start, -direction, 1 - radius)[0] is not None for t in eyes)
            eye_bowl = direction.y < -.4 and math.hypot(abs(skin.x) - .12088, z - .11889) < .109
            if front_eye or eye_bowl:
                continue
            covered += 1
            if not any(t.ray_cast(start, -direction, 1 - radius + .001)[0] is not None for t in [*trees, torso]):
                visible.append((round(z, 5), round(math.degrees(angle), 2), round(radius, 5)))
    return covered, visible


def test_eye_openings(pose, upper):
    front = Vector((0, 1, 0))
    collider = bvh(upper.data, [v.co for v in upper.data.vertices])
    eyes = colliders(pose, ['player_eye_L', 'player_eye_R'])
    rays, misses = 0, []
    for side in (-1, 1):
        for distance in (.0, .25, .65, .88, .97):
            for i in range(64):
                a = i * math.tau / 64
                start = Vector((side * .12088 + distance * .10462 * math.cos(a),
                                -1, .11889 + distance * .10462 * math.sin(a)))
                eye_depth = [d for t in eyes if (hit := t.ray_cast(start, front, 1.))[0] is not None
                             for d in [hit[3]]]
                if not eye_depth:
                    continue
                rays += 1
                if collider.ray_cast(start, front, min(eye_depth) + .0001)[0] is not None:
                    misses.append((side, distance, i))
    return rays, misses


def refit_pose(pose):
    col = bpy.data.collections[pose + ' • fitted cuts']
    col.hide_viewport = False
    col.hide_render = False
    bpy.context.view_layer.update()
    source = bpy.data.objects['Hood • ' + pose]
    bodice = bpy.data.objects['Bodice • ' + pose]
    mount = source.matrix_world.copy()
    native = {True: colliders(pose, UPPER_MESH), False: colliders(pose, LOWER_MESH)}
    lower_support = native[False] + colliders(pose, SUPPORT_MESH)
    old_seam = {tuple(v.co) for v in source.data.vertices if abs(v.co.z + .201) < .00002}
    old_rims = {tuple(p) for v in source.data.vertices if
                (p := v.co).y < -.410
                and abs(math.hypot(abs(p.x) - .12088, p.z - .11889) - .10462) < .00018}
    lower, lower_edges = section(source, False, native, lower_support, col)
    upper, upper_edges = section(source, True, native, lower_support, col)
    assert old_seam and old_seam <= {tuple(v.co) for v in lower.data.vertices}
    assert len(old_rims) >= 210 and old_rims <= {tuple(v.co) for v in upper.data.vertices}
    sampled, skin = check_shells(pose, upper, lower, bodice, mount, native, lower_support)
    eye_rays, blocked = test_eye_openings(pose, upper)
    print('FIT', pose, 'covered native shell rays', sampled, 'exposures', len(skin), skin[:20],
          'eye samples', eye_rays, 'blocked', len(blocked), blocked[:8], flush=True)
    assert len(blocked) == 0
    assert len(skin) == 0

    transforms, _ = transforms_for(pose)
    bottom, = [i for i, n in enumerate(SOURCE['nodes']) if n['name'] == 'Cosmetic Parent - Head Bottom Mesh']
    driver, = [i for i, n in enumerate(SOURCE['nodes']) if n['name'] == DRIVER_NAME]
    assert not below(bottom, driver) and below(SOURCE['anchors']['Hood'], driver)
    ground = stage(transforms[SOURCE['anchors']['Hood']].translation).z - mount.translation.z
    down = Matrix.Translation((0, 0, -ground))
    lower_mount = down @ BASIS @ transforms[bottom] @ BASIS.inverted()
    lower.data.transform(lower_mount.inverted() @ mount)
    lower.matrix_world = lower_mount
    upper['native_anchor'] = SOURCE['nodes'][SOURCE['anchors']['Hood']]['name']
    lower['native_anchor'] = SOURCE['nodes'][bottom]['name']

    # Show all three jaw samples in Blender with ordinary object animation.
    antennae = bpy.data.objects['Antennae • ' + pose]
    for obj in (upper, antennae):
        rest = obj.matrix_world.copy()
        obj.rotation_mode = 'QUATERNION'
        for (_, fraction), time in zip(MOUTH_STATES, (1, 13, 25)):
            delta = down @ BASIS @ jaw_delta(transforms, driver, fraction) @ BASIS.inverted() @ down.inverted()
            obj.matrix_world = delta @ rest
            obj.keyframe_insert(data_path='location', frame=time)
            obj.keyframe_insert(data_path='rotation_quaternion', frame=time)
        obj.matrix_world = rest
    return dict(headCoverageRays=sampled, uncoveredSamples=len(skin), exposedPoints=skin,
                eyeRays=eye_rays, eyeBlocked=len(blocked), preservedBodiceSeam=len(old_seam),
                preservedEyeRimVertices=len(old_rims),
                turnedJawEdges=[upper_edges, lower_edges])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = dist / 'semibot-full-fit-r2' / 'Boobees-full-outfit-fit.blend'
    bpy.ops.wm.open_mainfile(filepath=str(source))
    result = {pose: refit_pose(pose) for pose in poses}
    hidden = bpy.data.collections['Crouch • fitted cuts']
    hidden.hide_viewport = True
    hidden.hide_render = True
    scene = bpy.context.scene
    scene.frame_end = 25
    for frame, name in [(1, 'Closed'), (13, '22.5°'), (25, '45°')]:
        scene.timeline_markers.new(name, frame=frame)
    scene.frame_set(1)
    bpy.data.orphans_purge(do_recursive=True)
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'Boobees-head-fit.blend'))
    receipt = {'source': str(source.relative_to(dist)), 'rig': 'Native Semibot / build 26813769',
               'mode': 'Blender and native mesh probes, methodology-only',
               'poses': result}
    (output / 'head-fit-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
