"""Rebuild the sleeves over the measured native arm sections."""

import argparse
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_semibot_outfit import dist, lerp_rows, limb_check, local, poses, stage

SEGMENTS = 32
SECTIONS = (-.080, -.074, -.067, -.057, -.044, -.030, -.015, .0, .017, .037, .062, .089, .117,
            .147, .176, .205, .234, .263, .292, .320, .347, .373, .397, .419, .437, .453, .467,
            .480, .493, .506, .516, .525, .531, .536, .541, .546)
CAPS = ((-.081, .0), (-.074, .023), (-.055, .058), (.525, .021),
        (.533, .017), (.541, .014), (.546, .009), (.550, .0))


def sleeve_mesh(pose, side, old):
    sign = 1 if side == 'Right' else -1
    marker = side[0]
    _, points, triangles = local(pose, side + ' Sleeve', ['player_arm_' + marker])[0]
    native = BVHTree.FromPolygons(points, triangles, all_triangles=True)
    vertices = []
    faces = []
    for axis in SECTIONS:
        for i in range(SEGMENTS):
            angle = i * math.tau / SEGMENTS
            direction = Vector((0, math.cos(angle), math.sin(angle)))
            radius = 0.
            for sample in (axis - .003, axis, axis + .003):
                point = Vector((sign * sample, 0, 0))
                hit, _, _, _ = native.ray_cast(point + direction, -direction, 1.)
                if hit is not None:
                    radius = max(radius, direction.dot(hit - point))

            if -.060 < axis < .529:
                shoulder = .0055 * math.exp(-((axis - .073) / .13) ** 2)
                cuff = .004 * math.exp(-((axis - .472) / .012) ** 2)
                fold = .0014 * math.sin(4 * angle + axis * 11) * math.exp(-((axis - .12) / .22) ** 2)
                radius += .0085 + shoulder + cuff + fold
            else:
                cap_rows = CAPS[:3] if axis < 0 else CAPS[3:]
                radius = max(radius + .002, lerp_rows(cap_rows, axis))

            vertices.append(stage(Vector((sign * axis, radius * direction.y, radius * direction.z))))

    for section in range(len(SECTIONS) - 1):
        for j in range(SEGMENTS):
            k = (j + 1) % SEGMENTS
            a, b = section * SEGMENTS, (section + 1) * SEGMENTS
            faces.append((a + j, a + k, b + k, b + j))
    for axis, origin in [(-.081, 0), (.550, (len(SECTIONS) - 1) * SEGMENTS)]:
        tip = len(vertices)
        vertices.append(stage(Vector((sign * axis, 0, 0))))
        faces.extend((origin + j, origin + (j + 1) % SEGMENTS, tip) for j in range(SEGMENTS))

    mesh = bpy.data.meshes.new(side + ' Sleeve · native arm outline')
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(old.materials[0])
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    for face in bm.faces:
        face.smooth = True
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = dist / 'semibot-original-bodice' / 'Boobees-original-bodice.blend'
    bpy.ops.wm.open_mainfile(filepath=str(source))
    report = {}
    for pose in poses:
        report[pose] = {}
        for side in ('Left', 'Right'):
            name = side + ' Sleeve'
            obj = bpy.data.objects[name + ' • ' + pose]
            obj.data = sleeve_mesh(pose, side, obj.data)
            obj['asset_source'] = 'Sleeve shell fitted to the native arm profile'
            check = limb_check(obj, pose, 'Sleeve', side, 'player_arm_' + side[0])
            print(pose, name, check, flush=True)
            assert check['tested'] >= 2000 and not check['exposed'], check
            report[pose][name] = check
    bpy.data.orphans_purge(do_recursive=True)
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'Boobees-runtime-fit.blend'))
    (output / 'sleeve-fit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
