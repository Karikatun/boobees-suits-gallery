"""Refit the Sneaker Bee uppers in foot-anchor space and lift the sweater bands."""

import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_sneaker_release_assets import VIEWS, export_pack, render_icons
from finish_bee_sneaker_sleeves import brighter_palette
from fit_bee_sneaker_set import show
from refine_bee_sneaker_fit import woven_material


SHOES = {"shoe-left": (.016, -.013), "shoe-right": (-.027, .002)}
BAND_OFFSETS = {"sweater": .135, "sweater-crouch": .090}


def fit_upper(obj, lateral, forward):
    for vertex in obj.data.vertices:
        position = vertex.co
        # Keep the sole and toe box planted while centering the ankle opening.
        height = min(1, max(0, (position.z + .495) / .105))
        weight = height * height * (3 - 2 * height)
        position.x += weight * (lateral + .08 * position.x)
        position.y += weight * forward
    obj.data.update()


def lift_bands(obj, offset):
    palette = brighter_palette("sweater")
    bands = [(position + offset if 0 < position < .9 else position, color)
             for position, color in palette]
    obj.data.materials.clear()
    woven_material(obj, "sweater", palette=bands)


def main():
    blend, output = (Path(value).resolve() for value in sys.argv[-2:])
    output.mkdir(parents=True, exist_ok=True)
    assets = output / "assets"
    icons = output / "icons"
    assets.mkdir(exist_ok=True)
    icons.mkdir(exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    master = bpy.data.collections["Items · anchor local"]
    poses = [col for col in bpy.data.collections if col.name.startswith("Semibot · ")]
    objects = {obj.name: obj for obj in master.objects}
    show([master, *poses], master)
    bpy.context.view_layer.update()

    for name, (lateral, forward) in SHOES.items():
        fit_upper(objects[name], lateral, forward)
    for name, offset in BAND_OFFSETS.items():
        lift_bands(objects[name], offset)

    show([master, *poses], bpy.data.collections["Semibot · stand"])
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output / blend.name))

    receipt = export_pack(objects, assets)
    render_icons(master, objects, icons, {name: VIEWS[name] for name in (*SHOES, "sweater")})
    (output / "export.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
