"""Pack the approved New Year Bee geometry, textures and sprites for the mod."""

import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_new_year_bee import ITEMS, OUTPUT
from export_sneaker_release_assets import VIEWS, export_pack, render_icons, save_texture
from render_dual_suit_icon import portrait


def main():
    assets, icons, report = (Path(value).resolve() for value in sys.argv[-3:])
    assets.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(OUTPUT / "New-Year-Bee.blend"))
    group = bpy.data.collections["Items · anchor local"]
    objects = {obj.name: obj for obj in group.objects}
    data = export_pack(objects, assets, items=ITEMS, prefix="Winter")
    save_texture(objects["hat"], assets, 512, "Winter", "Emission Color", "-emission")
    art = assets.parent / "package-art"
    art.mkdir(exist_ok=True)
    bpy.data.objects["Studio floor"].hide_render = True
    stand = bpy.data.collections["Semibot · stand"]
    portrait("winter", list(stand.objects), bpy.context.scene.camera, art)
    views = {name: VIEWS[name] for name in ITEMS if name in VIEWS}
    views.update({"hat": (1.0, -5.0, 1.2), "scarf": (1.0, -5., 2.1),
                  "boot-left": (-2.2, -4.8, 1.4), "boot-right": (2.2, -4.8, 1.4)})
    render_icons(group, objects, icons, views=views, prefix="Winter")
    report.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
