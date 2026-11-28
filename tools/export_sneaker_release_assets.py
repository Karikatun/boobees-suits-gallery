"""Export only the sneaker costume meshes, base colors and item sprites."""

import gzip
import json
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_release_assets import pack_mesh
from fit_bee_sneaker_set import ITEMS, OUTPUT, world_bounds


VIEWS = {
    "antennae": (0.9, -4.8, 1.15),
    "sweater": (2.2, -4.8, 1.5),
    "abdomen": (2.1, -4.8, 1.9),
    "wings": (1.0, 4.8, 1.15),
    "sleeve-left": (1.4, -4.8, 2.2),
    "sleeve-right": (-1.4, -4.8, 2.2),
    "shoe-left": (-2.6, -4.8, 1.65),
    "shoe-right": (2.6, -4.8, 1.65),
}


def save_texture(obj, directory, limit, prefix, channel="Base Color", suffix=""):
    shader = obj.data.materials[0].node_tree.nodes.get("Principled BSDF")
    image_node = shader.inputs[channel].links[0].from_node
    image = image_node.image
    width, height = image.size
    assert width > 0 and height > 0, obj.name
    scale = min(1., limit / max(width, height))
    if scale != 1:
        image.scale(round(width * scale), round(height * scale))
    image.file_format = "PNG"
    image.filepath_raw = str(directory / f"{prefix}-{obj.name}{suffix}.png")
    image.save()


def export_pack(objects, directory, items=ITEMS, prefix="Sneaker"):
    receipt = {}
    with (directory / f"{prefix}.bin.gz").open("wb") as file:
        with gzip.GzipFile(fileobj=file, mode="wb", filename="", mtime=0) as writer:
            writer.write(b"BBS2")
            writer.write(bytes([len(items)]))
            for name in items:
                key = name.encode("ascii")
                compressed_name = f"{name}-crouch"
                writer.write(bytes([len(key)]) + key + bytes([compressed_name in objects]))
                receipt[name] = {}
                for pose in (name, compressed_name):
                    obj = objects.get(pose)
                    if obj is None:
                        continue
                    assert obj.matrix_world == Matrix.Identity(4), pose
                    data = pack_mesh(obj, Matrix.Identity(4), True)
                    writer.write(data)
                    count, indices = struct.unpack_from("<II", data)
                    receipt[name][pose] = {"vertices": count, "triangles": indices // 3}
                    save_texture(obj, directory, 512 if name in {"antennae", "sleeve-left", "sleeve-right"} else 1024, prefix)
    return receipt


def render_icons(group, objects, directory, views=VIEWS, prefix="Sneaker"):
    scene = bpy.context.scene
    camera = scene.camera
    for col in scene.collection.children:
        col.hide_render = col != group and col.name.startswith("Semibot · ")
    group.hide_viewport = group.hide_render = False
    bpy.data.objects["Studio floor"].hide_render = True
    scene.render.film_transparent = True
    scene.render.image_settings.color_mode = "RGBA"
    scene.cycles.samples = 24
    scene.render.resolution_x = scene.render.resolution_y = 256
    bpy.context.view_layer.update()

    for name, direction in views.items():
        obj = objects[name]
        for piece in objects.values():
            piece.hide_render = piece != obj
        lo, hi = world_bounds([obj])
        center = (lo + hi) * .5
        offset = Vector(direction).normalized()
        rot = (-offset).to_track_quat("-Z", "Y")
        points = [rot.inverted() @ (geo.co - center) for geo in obj.data.vertices]
        left, right = min(p.x for p in points), max(p.x for p in points)
        bottom, top = min(p.y for p in points), max(p.y for p in points)
        camera.location = center + offset * 4 + rot @ Vector(((left + right) * .5, (bottom + top) * .5, 0))
        camera.rotation_euler = rot.to_euler()
        camera.data.ortho_scale = max(right - left, top - bottom) / .86
        scene.render.filepath = str(directory / f"{prefix}-{name}.png")
        bpy.ops.render.render(write_still=True)


def main():
    assets, icons, report = (Path(value).resolve() for value in sys.argv[-3:])
    assets.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(OUTPUT / "Bee-Sneaker-Set.blend"))
    collection = bpy.data.collections["Items · anchor local"]
    objects = {obj.name: obj for obj in collection.objects}
    data = export_pack(objects, assets)
    render_icons(collection, objects, icons)
    report.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
