"""Render the real outfit pieces as transparent inventory thumbnails."""

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_semibot_outfit import setup_stage

VIEWS = {
    'Antennae': (['Antennae'], 23, 16, -9),
    'Hood': (['Hood'], 29, 11, 5),
    'HoodLower': (['Hood Lower'], 34, 26, -7),
    'Bodice': (['Bodice'], 36, 11, -3),
    'Wings': (['Wings'], 155, 14, -6),
    'Mantle': (['Hem'], 25, 21, 3),
    'SleeveLeft': (['Left Sleeve'], 37, 17, 34),
    'Sleeve': (['Right Sleeve'], -37, 17, -34),
    'SockLeft': (['Left Sock'], 22, 17, 34),
    'Sock': (['Right Sock'], -22, 17, -34),
}


def bounds(points):
    return [Vector(tuple(fn(p[i] for p in points) for i in range(3))) for fn in (min, max)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.frame_set(1)
    camera, stage = setup_stage()
    stage[0].hide_render = True
    scene.render.film_transparent = True
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.resolution_x = scene.render.resolution_y = 256
    scene.cycles.samples = 48
    group = bpy.data.collections['Stand • fitted cuts']
    objects = {obj.name.split(' • ')[0]: obj for obj in group.objects}
    authored = {name: obj.matrix_world.copy() for name, obj in objects.items()}
    center = Vector((0, 0, .90))

    for icon, (parts, azimuth, elevation, roll) in VIEWS.items():
        positions = [authored[name] @ v.co for name in parts for v in objects[name].data.vertices]
        low, high = bounds(positions)
        placement = (Matrix.Translation(center) @ Matrix.Scale(1. / max(high - low), 4)
                     @ Matrix.Translation(-.5 * (low + high)))
        for name, obj in objects.items():
            obj.hide_render = name not in parts
            if name in parts:
                obj.animation_data_clear()
                obj.matrix_world = placement @ authored[name]
        a, e = map(math.radians, (azimuth, elevation))
        direction = Vector((math.cos(e) * math.sin(a), -math.cos(e) * math.cos(a), math.sin(e)))
        camera.rotation_mode = 'QUATERNION'
        rotation = (-direction).to_track_quat('-Z', 'Y') @ Quaternion((0, 0, 1), math.radians(roll))
        camera.rotation_quaternion = rotation
        image_points = [rotation.inverted() @ (placement @ p - center) for p in positions]
        lo, hi = bounds(image_points)
        image_center = Vector((0.5 * (lo.x + hi.x), 0.5 * (lo.y + hi.y), 0))
        camera.location = center + direction * 5 + rotation @ image_center
        camera.data.ortho_scale = max(hi.x - lo.x, hi.y - lo.y) / .86
        scene.render.filepath = str(output / (icon + '.png'))
        bpy.ops.render.render(write_still=True)


if __name__ == '__main__':
    main()
