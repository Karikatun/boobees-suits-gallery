"""Trim the fused back-cloth flaps from the fitted Cast-Iron Boo-Bee wings."""

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mesh_surface_clip import carve_convex


def trim(fitted, source):
    mesh = fitted.data
    mesh.calc_loop_triangles()
    original = source.data
    original.calc_loop_triangles()
    assert len(original.loop_triangles) == len(mesh.loop_triangles)
    assert all(a.vertices[:] == b.vertices[:] for a, b in zip(original.loop_triangles, mesh.loop_triangles))

    # The source cut included the sides of the cape. The wing lobes extend
    # rearward from this boundary, with more clearance below the smaller lobe.
    planes = (lambda p: p[1] - .209, lambda p: p[1] + .72 * (p[2] - .148) - .218)
    vertices, lookup, faces, uvs, normals = [], {}, [], [], []
    trimmed = 0
    for tri in mesh.loop_triangles:
        corners = []
        for i in tri.loops:
            v = mesh.loops[i].vertex_index
            corners.append((*original.vertices[v].co, *mesh.vertices[v].co,
                            *mesh.corner_normals[i].vector, *mesh.uv_layers.active.data[i].uv))
        clipped, waste = carve_convex(corners, planes)
        trimmed += bool(waste)
        if clipped is None:
            continue
        for j in range(1, len(clipped) - 1):
            triangle = (clipped[0], clipped[j], clipped[j + 1])
            a, b, c = (Vector(p[3:6]) for p in triangle)
            if (b - a).cross(c - a).length < 1e-9:
                continue
            face = []
            for corner in triangle:
                position = corner[3:6]
                key = tuple(round(axis, 7) for axis in position)
                if key not in lookup:
                    lookup[key] = len(vertices)
                    vertices.append(position)
                face.append(lookup[key])
            if len(set(face)) != 3:
                continue
            faces.append(face)
            normals.extend(Vector(corner[6:9]).normalized() for corner in triangle)
            uvs.extend(corner[9:11] for corner in triangle)

    cleaned = bpy.data.meshes.new(mesh.name + ' · wing lobes')
    cleaned.from_pydata(vertices, [], faces)
    cleaned.materials.append(mesh.materials[0])
    layer = cleaned.uv_layers.new(name=mesh.uv_layers.active.name)
    for entry, uv in zip(layer.data, uvs):
        entry.uv = uv
    for polygon in cleaned.polygons:
        polygon.use_smooth = True
    cleaned.normals_split_custom_set(normals)
    cleaned.update()
    fitted.data = cleaned
    return {'inputTriangles': len(mesh.loop_triangles), 'trimmedTriangles': trimmed,
            'outputTriangles': len(faces)}


def main():
    original_blend, output, receipt = (Path(arg).resolve() for arg in sys.argv[-3:])
    with bpy.data.libraries.load(str(original_blend)) as (_, assets):
        assets.objects = ['Wings']
    source, = assets.objects
    report = {}
    for pose in ('Stand', 'Crouch'):
        report[pose] = trim(bpy.data.objects['Wings • ' + pose], source)
    bpy.data.objects.remove(source)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    receipt.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
