"""Export the approved outfit's anchor-local meshes and fabric into the plugin."""

import gzip
import json
import math
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_semibot_outfit import BASIS, SOURCE, poses, stage, transforms_for, unity

# In-game slot anchors. The lower hood and the hem use the identity-offset
# neighbors of their Blender mounts so neither replaces or hides the base mesh.
PARTS = {
    'Antennae': SOURCE['anchors']['Antennae'],
    'Hood': SOURCE['anchors']['Hood'],
    'Hood Lower': 101,
    'Bodice': SOURCE['anchors']['Bodice'],
    'Wings': SOURCE['anchors']['Bodice'],
    'Hem': 57,
    'Left Sleeve': SOURCE['anchors']['Left Sleeve'],
    'Right Sleeve': SOURCE['anchors']['Right Sleeve'],
    'Left Sock': SOURCE['anchors']['Left Sock'],
    'Right Sock': SOURCE['anchors']['Right Sock'],
}
assert SOURCE['nodes'][101]['name'] == 'Cosmetic Parent - Head Bottom'
assert SOURCE['nodes'][57]['name'] == 'Cosmetic Parent - Body Top Mesh'


def pack_mesh(obj, to_anchor, textured):
    mesh = obj.data
    mesh.calc_loop_triangles()
    layer = mesh.uv_layers.active
    assert (layer is not None) == textured
    normal_transform = to_anchor.to_3x3().inverted().transposed()
    positions = [unity(to_anchor @ v.co) for v in mesh.vertices]
    normals = [unity((normal_transform @ n.vector).normalized()) for n in mesh.corner_normals]
    lo, hi = (f(p.y for p in positions) for f in (min, max))
    result = {}
    indices = []
    agreement = 0.
    area = 0.
    for face in mesh.loop_triangles:
        a, b, c = (positions[mesh.loops[loop].vertex_index] for loop in face.loops)
        cross = (b - a).cross(c - a)
        area += cross.length
        if cross.dot(sum((normals[loop] for loop in face.loops), cross * 0)) >= 0:
            agreement += cross.length
        # The axis mapping is a rotation. Keep the exterior winding, as on the native game meshes.
        for loop in face.loops:
            i = mesh.loops[loop].vertex_index
            position = positions[i]
            uv = layer.data[loop].uv if textured else (.5, (position.y - lo) / (hi - lo))
            attrs = (*position, *normals[loop], *uv)
            assert all(math.isfinite(v) for v in attrs), obj.name
            indices.append(result.setdefault(attrs, len(result)))
    assert area > 0 and agreement / area > .96, (obj.name, agreement / area)
    assert len(result) < 65536
    result_data = b''.join(struct.pack('<8f', *item) for item in result)
    return struct.pack('<II', len(result), len(indices)) + result_data + struct.pack(f'<{len(indices)}H', *indices)


def image_bytes(name):
    images = [im for im in bpy.data.images if im.name == name or im.name.startswith(name + '.')]
    assert images and all(im.packed_file for im in images)
    payload = images[0].packed_file.data
    assert all(im.packed_file.data == payload for im in images)
    return payload


def write_swatch(path, color_at, height):
    img = bpy.data.images.new(path.stem, width=8, height=height, alpha=True)
    img.colorspace_settings.name = 'sRGB'

    def srgb(linear):
        return 12.92 * linear if linear <= .0031308 else 1.055 * linear ** (1 / 2.4) - .055

    rows = []
    for row in range(height):
        color = color_at(row / max(height - 1, 1))
        rows.extend([(*(srgb(c) for c in color[:3]), 1.)] * 8)
    img.pixels.foreach_set([c for px in rows for c in px])
    img.filepath_raw = str(path)
    img.file_format = 'PNG'
    img.save()


def main():
    output, receipt = (Path(arg).resolve() for arg in sys.argv[-2:])
    output.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    for pose in poses:
        bpy.data.collections[pose + ' • fitted cuts'].hide_viewport = False
    scene.frame_set(1)
    bpy.context.view_layer.update()
    targets = {}
    for pose in poses:
        transforms, visible = transforms_for(pose)
        src_ground = stage(transforms[SOURCE['anchors']['Hood']].translation).z
        render_ground = bpy.data.objects['Hood • ' + pose].matrix_world.translation.z
        to_floor = Matrix.Translation((0, 0, render_ground - src_ground))
        targets[pose] = {}
        for name, index in PARTS.items():
            assert visible[index], (pose, name)
            targets[pose][name] = to_floor @ BASIS @ transforms[index] @ BASIS.inverted()

    report = {}
    with (output / 'Outfit.bin.gz').open('wb') as payload:
        with gzip.GzipFile(fileobj=payload, mode='wb', filename='', mtime=0) as writer:
            writer.write(b'BBS1')
            writer.write(bytes([len(PARTS)]))
            for name in PARTS:
                tag = name.encode('ascii')
                writer.write(bytes([len(tag)]))
                writer.write(tag)
                report[name] = {}
                for pose in poses:
                    obj = bpy.data.objects[name + ' • ' + pose]
                    relative = targets[pose][name].inverted() @ obj.matrix_world
                    error = max(abs(a - b) for ra, rb in zip(relative, Matrix.Identity(4)) for a, b in zip(ra, rb))
                    assert error < .00002, (name, pose, error)
                    data = pack_mesh(obj, relative, not name.endswith(('Sleeve', 'Sock')))
                    writer.write(data)
                    corners, indices = struct.unpack_from('<II', data)
                    report[name][pose] = {'vertices': corners, 'triangles': indices // 3}

    (output / 'Fabric.png').write_bytes(image_bytes('color.png'))
    (output / 'FabricNormal.png').write_bytes(image_bytes('normal.png'))
    sleeve = bpy.data.objects['Right Sleeve • Stand'].data.materials[0]
    sleeve_tint = sleeve.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value
    socks = bpy.data.objects['Right Sock • Stand'].data.materials[0]
    ramp = next(n.color_ramp for n in socks.node_tree.nodes if n.type == 'VALTORGB')
    write_swatch(output / 'SleeveFabric.png', lambda _: sleeve_tint, 1)
    write_swatch(output / 'SockFabric.png', ramp.evaluate, 512)
    receipt.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('Exported', len(PARTS), 'parts with checked anchors for both poses')


if __name__ == '__main__':
    main()
