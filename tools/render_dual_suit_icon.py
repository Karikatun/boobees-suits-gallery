"""Render transparent images of both outfits for the release icon."""

import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_bee_sneaker_set import OUTPUT, world_bounds
from fit_semibot_outfit import SOURCE, add_stock, setup_stage, stage, transforms_for


def portrait(name, group, camera, directory):
    scene = bpy.context.scene
    scene.render.film_transparent = True
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.resolution_x = scene.render.resolution_y = 430
    scene.cycles.samples = 24
    bpy.context.view_layer.update()
    lo, hi = world_bounds(group)
    center = (lo + hi) * .5
    direction = Vector((1.45 if name == "sneaker" else -1.45, -5., .36))
    camera.location = center + direction
    camera.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    camera.data.ortho_scale = (hi.z - lo.z) * 1.07
    scene.render.filepath = str(directory / f"{name}.png")
    bpy.ops.render.render(write_still=True)


def main():
    old, directory = (Path(value).resolve() for value in sys.argv[-2:])
    directory.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(old))
    current = bpy.data.collections["Stand • fitted cuts"]
    original = bpy.data.collections.new("Stock for package thumbnail")
    bpy.context.scene.collection.children.link(original)
    transforms, visible = transforms_for("Stand")
    hood = bpy.data.objects["Hood • Stand"]
    offset = stage(transforms[SOURCE["anchors"]["Hood"]].translation).z - hood.matrix_world.translation.z
    retained = add_stock(original, transforms, visible, offset)
    for name, obj in retained.items():
        obj.hide_render = not name.startswith(("player_eye", "player_iris", "player_leg"))
    camera, stage_objects = setup_stage()
    stage_objects[0].hide_render = True
    portrait("boo", list(current.objects) + [o for o in original.objects if not o.hide_render], camera, directory)

    bpy.ops.wm.open_mainfile(filepath=str(OUTPUT / "Bee-Sneaker-Set.blend"))
    bpy.data.objects["Studio floor"].hide_render = True
    current = bpy.data.collections["Semibot · stand"]
    portrait("sneaker", list(current.objects), bpy.context.scene.camera, directory)


if __name__ == "__main__":
    main()
