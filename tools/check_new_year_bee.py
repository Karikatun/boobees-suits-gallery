"""Verify the winter meshes, shoulder coverage and face clearance."""

import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_bee_sneaker_exports as check
from finish_bee_sneaker_sleeves import uncovered
from fit_new_year_bee import ITEMS, OUTPUT
from refine_bee_sneaker_fit import tree


def check_scene():
    bpy.ops.wm.open_mainfile(filepath=str(OUTPUT / "New-Year-Bee.blend"))
    result = {}
    for group in bpy.data.collections:
        if not group.name.startswith("Semibot · "):
            continue
        label = group.name.split(" · ")[1]
        pieces = {obj.name.split(".")[0].removesuffix("-crouch"): obj for obj in group.objects}
        assert set(ITEMS) <= pieces.keys(), label
        torso = pieces["sweater"]
        scarf = pieces["scarf"]
        assert max(abs(torso.matrix_world[i][j] - scarf.matrix_world[i][j])
                   for i in range(4) for j in range(4)) < 1e-6, label
        eyes = [check.tree(pieces[f"player_eye_{side}"]) for side in ("L", "R")]
        hat = check.tree(pieces["hat"])
        neck = check.tree(scarf)
        overlaps = sum(bool(surface.overlap(eye)) for surface in (hat, neck) for eye in eyes)
        assert overlaps == 0, (label, overlaps)
        outside = {}
        for side, letter in (("left", "L"), ("right", "R")):
            arm = pieces[f"player_arm_{letter}"]
            sleeve = pieces[f"sleeve-{side}"]
            transform = sleeve.matrix_world.inverted()
            outside[side] = uncovered(tree(sleeve, transform @ sleeve.matrix_world),
                                      arm.data, transform @ arm.matrix_world)
        assert all(count == 0 for count in outside.values()), (label, outside)
        result[label] = {"equippedItems": len(ITEMS), "faceIntersections": overlaps, "outsideSleeveVertices": outside}
    assert len(result) == 6
    return result


def main():
    check.OUTPUT = OUTPUT
    report = check_scene()
    fit = json.loads((OUTPUT / "fit-receipt.json").read_text(encoding="utf-8"))
    exports = {name: check.validate_file(name, stats["fittedTriangles"]) for name, stats in fit.items()}
    for name, stats in fit.items():
        if stats["crouchTriangles"] is not None:
            key = name + "-crouch"
            exports[key] = check.validate_file(key, stats["crouchTriangles"])
    (OUTPUT / "verification.json").write_text(
        json.dumps({"poses": report, "fbx": exports}, indent=2) + "\n", encoding="utf-8")
    print(f"Checked {len(report)} fitted poses and {len(exports)} FBX exports")


if __name__ == "__main__":
    main()
