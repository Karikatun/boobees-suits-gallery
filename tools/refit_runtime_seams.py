"""Fit the assembled suit's collar and wing roots on the Semibot torso."""

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_semibot_outfit import bvh, poses, smooth


def points(obj):
    return [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]


def write_points(obj, positions):
    to_local = obj.matrix_world.inverted()
    for vertex, position in zip(obj.data.vertices, positions):
        vertex.co = to_local @ position
    obj.data.update()


def overlap_collar(bodice, collar):
    body_points = points(bodice)
    collar_points = points(collar)
    neckline = max(p.z for p in body_points)
    lower_edge = min(p.z for p in collar_points)

    for p in body_points:
        blend = smooth(neckline - .081, neckline, p.z)
        p.z += .044 * blend
        radius = p.to_2d().length
        if radius > .1:
            p.x *= 1. + .024 * blend / radius
            p.y *= 1. + .024 * blend / radius
    for p in collar_points:
        blend = 1. - smooth(lower_edge, lower_edge + .062, p.z)
        p.z -= .028 * blend
        radius = p.to_2d().length
        if radius > .1:
            p.x *= 1. + .011 * blend / radius
            p.y *= 1. + .011 * blend / radius
    write_points(bodice, body_points)
    write_points(collar, collar_points)
    return round(max(p.z for p in body_points) - min(p.z for p in collar_points), 4)


def seat_wings(wings, bodice):
    body_points = points(bodice)
    back = bvh(bodice.data, body_points)
    lower = min(p.z for p in body_points)
    upper = max(p.z for p in body_points)
    wing_points = points(wings)
    report = {}

    for side in (-1, 1):
        pair = [p for p in wing_points if p.x * side > 0.]
        inner = min(abs(p.x) for p in pair)
        root = [p for p in pair if abs(p.x) <= inner + .040]
        root_depth = sum(p.y for p in root) / len(root)
        inside = []
        for p in pair:
            span = abs(p.x) - inner
            p.x = side * (.154 + 1.13 * span)
            p.z = min(upper - .013, max(lower + .011, p.z)) if span < .030 else p.z
            sample_z = min(upper - .018, max(lower + .017, p.z))
            surface = back.ray_cast(Vector((p.x, 1., sample_z)), Vector((0., -1., 0.)), 1.)[0]
            root_weight = 1. - smooth(.020, .115, span)
            free_depth = p.y - .033
            if surface is not None:
                sewn_depth = surface.y - .038 + .24 * (p.y - root_depth)
                p.y = free_depth + root_weight * (sewn_depth - free_depth)
                if span <= .020:
                    inside.append(surface.y - p.y)
            else:
                p.y = free_depth
        assert inside and min(inside) > .012, (side, min(inside, default=0.))
        report[str(side)] = {'rootVertices': len(inside), 'minRootDepth': round(min(inside), 4)}

    write_points(wings, wing_points)
    return report


def main():
    output, receipt = (Path(arg).resolve() for arg in sys.argv[-2:])
    for pose in poses:
        bpy.data.collections[pose + ' • fitted cuts'].hide_viewport = False
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()
    report = {}
    for pose in poses:
        bodice = bpy.data.objects['Bodice • ' + pose]
        collar = bpy.data.objects['Hood Lower • ' + pose]
        wings = bpy.data.objects['Wings • ' + pose]
        report[pose] = {'collarOverlap': overlap_collar(bodice, collar), 'wings': seat_wings(wings, bodice)}
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    receipt.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
