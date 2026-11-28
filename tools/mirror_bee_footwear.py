"""Mirror the fitted left boot or shoe into the right foot's local space."""

import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_sneaker_release_assets import ITEMS as SNEAKER_ITEMS, VIEWS, export_pack, render_icons
from fit_bee_sneaker_set import show
from fit_new_year_bee import ITEMS as WINTER_ITEMS


def mirror_footwear(source, target):
    assert source.matrix_world == target.matrix_world == Matrix.Identity(4)
    assert not source.data.has_custom_normals
    original = target.data
    mirror = source.data.copy()
    mirror.name = f"{target.name} · mirrored {source.name}"
    mirror.transform(Matrix.Diagonal((-1., 1., 1., 1.)))
    mirror.flip_normals()
    mirror.update()

    source_uv = source.data.uv_layers.active.data
    mirror_uv = mirror.uv_layers.active.data
    for original_face, mirrored_face in zip(source.data.polygons, mirror.polygons, strict=True):
        by_vertex = {source.data.loops[i].vertex_index: source_uv[i].uv for i in original_face.loop_indices}
        for loop in mirrored_face.loop_indices:
            assert mirror_uv[loop].uv == by_vertex[mirror.loops[loop].vertex_index]

    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.data == original:
            obj.data = mirror


def main():
    blend, output = (Path(value).resolve() for value in sys.argv[-2:])
    assets, icons = output / "assets", output / "icons"
    assets.mkdir(parents=True, exist_ok=True)
    icons.mkdir(exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    master = bpy.data.collections["Items · anchor local"]
    poses = [group for group in bpy.data.collections if group.name.startswith("Semibot · ")]
    objects = {obj.name: obj for obj in master.objects}
    show([master, *poses], master)
    bpy.context.view_layer.update()
    if "boot-left" in objects:
        left, right = "boot-left", "boot-right"
        prefix, items, view = "Winter", WINTER_ITEMS, (2.2, -4.8, 1.4)
    else:
        left, right = "shoe-left", "shoe-right"
        prefix, items, view = "Sneaker", SNEAKER_ITEMS, VIEWS[right]
    mirror_footwear(objects[left], objects[right])

    show([master, *poses], bpy.data.collections["Semibot · stand"])
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output / blend.name))
    report = export_pack(objects, assets, items=items, prefix=prefix)
    render_icons(master, objects, icons, {right: view}, prefix=prefix)
    (output / "export.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
