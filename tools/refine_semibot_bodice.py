"""Give the two reliefs a measured pear profile on the latest Boobees outfit."""

import argparse
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_semibot_outfit import (
    SOURCE, add_stock, bvh, collection, dist, mix, point_camera, poses, set_mesh_world,
    setup_stage, smooth, stage, transforms_for,
)

# Height relative to the existing bodice seams, followed by half-width and depth.
PEAR_PROFILE = (
    (.10, .0, .0), (.17, .040, .032), (.24, .079, .090), (.33, .106, .131),
    (.41, .103, .127), (.50, .088, .102), (.61, .065, .079), (.72, .043, .048),
    (.83, .026, .030), (.93, .014, .014), (.985, .0, .0),
)
FORWARD = Vector((0, 1, 0))


def profile_tangent(i, column):
    if i in (0, len(PEAR_PROFILE) - 1):
        return 0.
    a, b, c = PEAR_PROFILE[i - 1:i + 2]
    left = (b[column] - a[column]) / (b[0] - a[0])
    right = (c[column] - b[column]) / (c[0] - b[0])
    return 2 * left * right / (left + right) if left * right > 0 else 0.


def section_profile(t):
    if t <= PEAR_PROFILE[0][0] or t >= PEAR_PROFILE[-1][0]:
        return 0., 0.
    for i, (a, b) in enumerate(zip(PEAR_PROFILE, PEAR_PROFILE[1:])):
        lo, hi = a[0], b[0]
        if lo <= t <= hi:
            q = (t - lo) / (hi - lo)
            weight = q * q * (3 - 2 * q)
            return tuple(mix(a[k], b[k], weight)
                         + (hi - lo) * (q * (1 - q) ** 2 * profile_tangent(i, k)
                                        - q * q * (1 - q) * profile_tangent(i + 1, k))
                         for k in (1, 2))


def tissue_depth(surface, x, z):
    hit = surface.ray_cast(Vector((x, -1, z)), FORWARD, 1.)[0]
    return -hit.y if hit is not None else None


def refine_front_mesh(mesh, mount, lo, hi):
    """Add vertices to the front relief without splitting either seam."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    for threshold in (.045, .026):
        edges = []
        for edge in bm.edges:
            a, b = [mount @ v.co for v in edge.verts]
            midpoint = (a + b) * .5
            if (not edge.is_boundary and (a - b).length > threshold and abs(midpoint.x) < .268
                    and midpoint.y < -.129 and lo + .012 < midpoint.z < hi - .012):
                edges.append(edge)
        bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1, use_grid_fill=True)
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
    for p in bm.faces:
        p.smooth = True
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


def new_bodice(obj, native, crouch):
    mount = obj.matrix_world.copy()
    original = obj.data
    points = [mount @ v.co for v in original.vertices]
    lo, hi = (fn(p.z for p in points) for fn in (min, max))
    original_tree = bvh(original, points)
    upper_skin = [bvh(o.data, [v.co for v in o.data.vertices]) for name, o in native.items()
                  if name.startswith(('player_body_', 'player_health_', 'player_head_bot'))]
    mesh = original.copy()
    mesh.name = 'Pear-profile bodice'
    refine_front_mesh(mesh, mount, lo, hi)
    positions = []
    for vertex in mesh.vertices:
        p = mount @ vertex.co
        x, y, z = p
        depth = -y
        side = abs(x)
        t = (z - lo) / (hi - lo)
        horizontal = smooth(.125, .209, depth) * (1 - smooth(.220, .295, side))
        vertical = smooth(.045, .165, t) * (1 - smooth(.935, .994, t))
        mask = horizontal * vertical
        if mask < .000001:
            positions.append(p)
            continue
        center = mix(.120 if not crouch else .107, .102 if not crouch else .095, smooth(.40, .90, t))
        width, volume = section_profile(t)
        if crouch:
            width *= .74
            volume *= .86
        u = abs(side - center) / max(width, .000001)
        relief = volume * max(0., 1 - u * u) ** 1.33

        # This is the fabric underneath both reliefs, rounded to the actual torso.
        upper_fabric = (.296 if not crouch else .283) * math.sqrt(max(.12, 1 - (side / .326) ** 2))
        at_upper_seam = tissue_depth(original_tree, x, mix(lo, hi, .995))
        if at_upper_seam is not None:
            upper_fabric = mix(upper_fabric, at_upper_seam, smooth(.66, .995, t))
        skin = [hit for tree in upper_skin if (hit := tissue_depth(tree, x, z)) is not None]
        cloth_base = max(upper_fabric, max(skin, default=0.) + .015)
        adjacent = [hit for dx, dz in ((-.018, 0), (.018, 0), (0, -.015), (0, .015))
                    if (hit := tissue_depth(original_tree, x + dx, z + dz)) is not None]
        fold = depth - sum(adjacent) / len(adjacent) if adjacent else 0.
        fold = mix(.55, .20, smooth(.0, .07, relief)) * min(.013, max(-.013, fold))
        aim = max(cloth_base + .003, cloth_base + relief + fold)
        depth = max(mix(depth, aim, mask), max(skin, default=0.) + .012)
        positions.append(Vector((x, -depth, z)))

    updated_tree = bvh(mesh, positions)
    tested = 0
    misses = []
    for row in range(1, 76):
        t = row / 76
        z = mix(lo, hi, t)
        for col in range(91):
            x = mix(-.278, .278, col / 90)
            native_hits = [d for tr in upper_skin if (d := tissue_depth(tr, x, z)) is not None]
            if not native_hits:
                continue
            skin = max(native_hits)
            before = tissue_depth(original_tree, x, z)
            if before is None or before < skin - .0005:
                continue
            after = tissue_depth(updated_tree, x, z)
            tested += 1
            if after is None or after < skin - .0005:
                misses.append((round(x, 4), round(t, 4)))

    def measure(surface, t):
        z = mix(lo, hi, t)
        depths = [(i * .002, tissue_depth(surface, i * .002, z)) for i in range(124)]
        # The cross-section's width where the projecting form is at least .036 in front of its margins.
        base = max(depths[0][1], depths[-1][1])
        relief = [x for x, depth in depths if depth is not None and depth - base >= .036]
        return round(max(relief) - min(relief), 4) if relief else 0.

    before = [measure(original_tree, t) for t in (.39, .69)]
    after = [measure(updated_tree, t) for t in (.39, .69)]
    differences = {'beforeLowerUpperWidths': before, 'afterLowerUpperWidths': after,
                   'torsoRays': tested, 'newExposures': len(misses)}
    print('PEAR', 'Crouch' if crouch else 'Stand', differences, misses[:18], flush=True)
    assert tested > 3000 and not misses, (tested, misses[:18])
    assert after[0] > .05 and after[1] < before[1] * .5, (before, after)

    keep = {tuple(p) for p in points if abs(p.z - lo) < .00002 or abs(p.z - hi) < .00002}
    assert keep <= {tuple(p) for p in positions}
    obj.data = mesh
    set_mesh_world(obj, positions, mount)
    obj['front_profile'] = 'Pear-shaped pair, tapered from the upper attachment to the rounded lower third'
    return original, differences


def show_frame(camera, output, name, z, azimuth):
    target = Vector((0, -.019, z))
    rad = math.radians(azimuth)
    camera.location = target + Vector((5 * math.sin(rad), -5 * math.cos(rad), .185))
    point_camera(camera, target)
    bpy.context.scene.render.filepath = str(output / (name + '.png'))
    bpy.ops.render.render(write_still=True)


def preview_pose(pose, output, camera):
    transforms, visible = transforms_for(pose)
    hood = bpy.data.objects['Hood • ' + pose]
    bodice = bpy.data.objects['Bodice • ' + pose]
    ground = stage(transforms[SOURCE['anchors']['Hood']].translation).z - hood.matrix_world.translation.z
    temp = collection(pose + ' • preview')
    native = add_stock(temp, transforms, visible, ground)
    old, report = new_bodice(bodice, native, pose == 'Crouch')
    after = bodice.data
    bodice.data = old
    target = hood.matrix_world.translation.z - (.21 if pose == 'Stand' else .18)
    label = pose.lower()
    show_frame(camera, output, label + '-before', target, 43)
    bodice.data = after
    show_frame(camera, output, label + '-front', target, 5)
    show_frame(camera, output, label + '-side', target, 43)
    for obj in native.values():
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(temp)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--draft', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = dist / 'semibot-head-fit' / 'Boobees-head-fit.blend'
    bpy.ops.wm.open_mainfile(filepath=str(source))
    scene = bpy.context.scene
    scene.frame_set(1)
    camera, lights = setup_stage(args.draft)
    camera.data.ortho_scale = 1.14
    scene.render.resolution_x = 420 if args.draft else 615
    scene.render.resolution_y = 420 if args.draft else 615
    collections = {pose: bpy.data.collections[pose + ' • fitted cuts'] for pose in poses}
    records = {}
    for pose in poses:
        for selection, col in collections.items():
            col.hide_viewport = selection != pose
            col.hide_render = selection != pose
        bpy.context.view_layer.update()
        records[pose] = preview_pose(pose, output, camera)
    receipt = {'source': source.name, 'poses': records,
               'method': 'Baseline/candidate Blender probes only, methodology-only'}
    (output / 'pear-fit-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    if args.draft:
        return
    for obj in lights:
        bpy.data.objects.remove(obj, do_unlink=True)
    for pose, col in collections.items():
        col.hide_viewport = pose != 'Stand'
        col.hide_render = pose != 'Stand'
    bpy.data.orphans_purge(do_recursive=True)
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'Boobees-pear-bodice.blend'))


if __name__ == '__main__':
    main()
