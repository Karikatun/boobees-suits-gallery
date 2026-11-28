"""Preview the existing outfit on the stock voice-driven jaw, at three opening angles."""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_semibot_outfit import (
    BASIS, SOURCE, add_stock, collection, dist, point_camera, poses, setup_stage, stage, transforms_for,
)

DRIVER_NAME = 'code_head_top'
# PlayerAvatarTalkAnimation on the installed gameplay prefab, resources.assets:2188477.
MAX_OPEN_ANGLE = 45.
MOUTH_STATES = (('closed', 0.), ('speaking', .5), ('wide', 1.))
UPPER_MOUNTS = ('Hood', 'Antennae')


def below(node, ancestor):
    while node is not None:
        if node == ancestor:
            return True
        node = SOURCE['nodes'][node]['parent']
    return False


def jaw_delta(transforms, driver, fraction):
    parent = transforms[SOURCE['nodes'][driver]['parent']]
    local = parent.inverted() @ transforms[driver]
    pos, _, scale = local.decompose()
    target = Matrix.Translation(pos) @ Matrix.Rotation(math.radians(-MAX_OPEN_ANGLE * fraction), 4, 'X')
    return parent @ target @ Matrix.Diagonal((*scale, 1.)) @ transforms[driver].inverted()


def pose_views(pose, output, camera, apparel, driver):
    transforms, visible = transforms_for(pose)
    hood = apparel['Hood']
    start = {part: obj.matrix_world.copy() for part, obj in apparel.items()}
    native_hood = transforms[SOURCE['anchors']['Hood']]
    ground = stage(native_hood.translation).z - start['Hood'].translation.z
    down = Matrix.Translation((0, 0, -ground))
    top_mounts = [part for part in UPPER_MOUNTS if below(SOURCE['anchors'][part], driver)]
    assert tuple(top_mounts) == UPPER_MOUNTS
    assert not below(SOURCE['anchors']['Bodice'], driver)

    front_points = [p for v in hood.data.vertices if abs((p := start['Hood'] @ v.co).x) < .12 and p.y < -.20]
    seam_z = min(p.z for p in front_points)
    front = [p for p in front_points if p.z < seam_z + .009]
    aim = Vector((0, -.015, start['Hood'].translation.z + .066))
    angle = math.radians(18.)
    camera.location = aim + Vector((5 * math.sin(angle), -5 * math.cos(angle), .12))
    point_camera(camera, aim)

    measured = {}
    for label, fraction in MOUTH_STATES:
        delta = jaw_delta(transforms, driver, fraction)
        moved = [delta @ tr if below(i, driver) else tr for i, tr in enumerate(transforms)]
        stage_delta = down @ BASIS @ delta @ BASIS.inverted() @ down.inverted()
        for part in top_mounts:
            apparel[part].matrix_world = stage_delta @ start[part]
        mocap = collection(pose + ' • stock jaw preview')
        stock = add_stock(mocap, moved, visible, ground)

        lift = [(stage_delta @ p).z - p.z for p in front]
        measured[label] = {'rotationDegrees': -MAX_OPEN_ANGLE * fraction,
                           'frontHoodEdgeLift': [round(min(lift), 5), round(max(lift), 5)]}
        if fraction:
            assert min(lift) > .1, measured[label]
        scene = bpy.context.scene
        scene.render.filepath = str(output / f'{pose.lower()}-{label}.png')
        bpy.ops.render.render(write_still=True)

        for obj in stock.values():
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(mocap)

    for part in top_mounts:
        apparel[part].matrix_world = start[part]
    return measured


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--draft', action='store_true')
    parser.add_argument('--outfit', type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = (args.outfit or dist / 'semibot-full-fit-r2' / 'Boobees-full-outfit-fit.blend').resolve()
    bpy.ops.wm.open_mainfile(filepath=str(source))
    driver, = [i for i, n in enumerate(SOURCE['nodes']) if n['name'] == DRIVER_NAME]
    camera, _ = setup_stage(args.draft)
    camera.data.ortho_scale = 1.24
    scene = bpy.context.scene
    scene.render.resolution_x = 410 if args.draft else 600
    scene.render.resolution_y = 420 if args.draft else 620
    outfits = {pose: bpy.data.collections[pose + ' • fitted cuts'] for pose in poses}
    scene.frame_set(1)
    results = {}
    for pose, outfit in outfits.items():
        for other, col in outfits.items():
            col.hide_render = other != pose
            col.hide_viewport = other != pose
        bpy.context.view_layer.update()
        apparel = {obj.name.split(' • ')[0]: obj for obj in outfit.objects}
        assert len(apparel) == 9 + ('Hood Lower' in apparel)
        for part in UPPER_MOUNTS:
            apparel[part].animation_data_clear()
        results[pose] = pose_views(pose, output, camera, apparel, driver)
    receipt = dict(outfit=source.name, avatarBuild=26813769, poses=results,
                   rotationDriver=DRIVER_NAME, maxRotationDegrees=MAX_OPEN_ANGLE,
                   runtimeComponent='PlayerAvatarTalkAnimation / resources.assets:2188477',
                   implementation='Offline samples of the installed voice-driven jaw rotation')
    (output / 'mouth-fit.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
