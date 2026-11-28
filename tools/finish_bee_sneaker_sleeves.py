"""Fit full shoulder sleeves and bake the brighter outfit palette."""

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_bee_sneaker_set import export, show, triangle_count
from refine_bee_sneaker_fit import FABRIC, render_all, tree, uniform_uv, woven_material


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist/bee-sneaker-set"
BASELINE = ROOT / ".local/bee-full-sleeves-baseline"
GOLD = (.98, .405, .008)
COCOA = (.041, .022, .016)
SLEEVE_DYES = [
    (0, GOLD), (.784, COCOA), (.829, GOLD), (.857, COCOA),
    (.895, GOLD), (.918, COCOA),
]
PROFILE = [
    (-.096, .026), (-.089, .045), (-.074, .064), (-.055, .079),
    (-.033, .087), (-.009, .091), (.026, .091), (.072, .087),
    (.122, .081), (.182, .073), (.242, .065), (.300, .057),
    (.358, .050), (.406, .043), (.439, .043), (.461, .040),
    (.481, .039), (.505, .036), (.531, .033), (.545, .027),
    (.557, .016),
]


def name_id(obj):
    return obj.name.split(".")[0]


def arm_surfaces(obj, poses, side):
    name = f"player_arm_{side}"
    rows = []
    for group in poses:
        sleeve = next(o for o in group.objects if o.data == obj.data)
        arm = next(o for o in group.objects if name_id(o) == name)
        rows.append((group.name, group, sleeve, arm, sleeve.matrix_world.inverted() @ arm.matrix_world))
    return rows


def fitted_sleeve(obj, arms, sign):
    stock = [tree(arm, transform) for _, _, _, arm, transform in arms]
    generated = tree(obj, Matrix.Identity(4))
    count = 36
    vertices = []
    for axial, radius_hint in PROFILE:
        for index in range(count):
            angle = index * math.tau / count
            radial = Vector((0, math.cos(angle), math.sin(angle)))
            origin = Vector((sign * axial, 0, 0)) + radial
            _, _, _, source_hit = generated.ray_cast(origin, -radial, 1)
            design_variation = .24 * max(-.010, min(.024, 1 - source_hit - radius_hint)) if source_hit is not None else 0
            radius = radius_hint + design_variation
            for surface in stock:
                _, _, _, native_hit = surface.ray_cast(origin, -radial, 1)
                if native_hit is not None:
                    radius = max(radius, 1 - native_hit + .013)
            point = Vector((sign * axial, 0, 0)) + radius * radial
            vertices.append(tuple(point))
    faces = []
    for ring in range(len(PROFILE) - 1):
        for i in range(count):
            j = (i + 1) % count
            a, b = ring * count, (ring + 1) * count
            faces.append((a + i, a + j, b + j, b + i))
    # Rounded caps turn the shoulder and mitten into a single closed shell.
    shoulder, mitten = len(vertices), len(vertices) + 1
    vertices.extend([(sign * -.102, 0, 0), (sign * .563, 0, 0)])
    last = (len(PROFILE) - 1) * count
    for i in range(count):
        j = (i + 1) % count
        faces.extend([(shoulder, i, j), (mitten, last + j, last + i)])
    mesh = bpy.data.meshes.new(obj.name + " · full shoulder sleeve")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    assert all(edge.is_manifold for edge in bm.edges), obj.name
    bm.to_mesh(mesh)
    bm.free()
    for face in mesh.polygons:
        face.use_smooth = True
    return mesh


def uncovered(sleeve_tree, mesh, transform):
    exposed = 0
    for vertex in mesh.vertices:
        point = transform @ vertex.co
        nearest, normal, _, _ = sleeve_tree.find_nearest(point)
        exposed += nearest is None or (point - nearest).dot(normal) > .003
    return exposed


def check_sleeve(obj, arms, before, after):
    cases = {}
    for name, group, sleeve, arm, trans in arms:
        torso = next(o for o in group.objects if name_id(o).startswith("sweater"))
        sweater_local = tree(torso, sleeve.matrix_world.inverted() @ torso.matrix_world)
        cases[name] = {
            "nativeArmVertices": len(arm.data.vertices),
            "outsideOldSleeve": uncovered(before, arm.data, trans),
            "outsideFullSleeve": uncovered(after, arm.data, trans),
            "intersectsSweaterAtShoulder": bool(after.overlap(sweater_local)),
        }
    assert all(case["outsideFullSleeve"] == 0 for case in cases.values()), (obj.name, cases)
    assert all(case["intersectsSweaterAtShoulder"] for case in cases.values()), (obj.name, cases)
    return cases


def brighter_palette(base):
    return [(at, color if color[0] < .15 else ((.94, .378, .007) if base == "abdomen" else GOLD))
            for at, color in FABRIC[base]]


def brighten_shoe_or_antenna(obj):
    for material in obj.data.materials:
        shader = material.node_tree.nodes.get("Principled BSDF")
        image_node = shader.inputs["Base Color"].links[0].from_node
        original = image_node.image
        rgba = np.empty(len(original.pixels), dtype=np.float32)
        original.pixels.foreach_get(rgba)
        pixels = rgba.reshape(-1, 4)
        red, green, blue = (pixels[:, i].copy() for i in range(3))
        warm = np.clip((red - blue - .02) / .27, 0, 1) * np.clip((green - blue) / .17, 0, 1)
        warm *= np.clip((green / np.maximum(red, .001) - .24) / .3, 0, 1)
        pixels[:, 0] = np.minimum(1, red * (1 + .12 * warm))
        pixels[:, 1] = np.minimum(1, green * (1 + .11 * warm))
        pixels[:, 2] = blue * (1 - .42 * warm)
        image = bpy.data.images.new(obj.name + " · saturated honey color", *original.size, alpha=True)
        image.colorspace_settings.name = original.colorspace_settings.name
        image.pixels.foreach_set(rgba)
        image.update()
        image.pack()
        image_node.image = image


def main():
    bpy.ops.wm.open_mainfile(filepath=str(BASELINE / "Bee-Sneaker-Set.blend"))
    scene = bpy.context.scene
    master = bpy.data.collections["Items · anchor local"]
    poses = sorted((g for g in bpy.data.collections if g.name.startswith("Semibot · ")), key=lambda g: g.name)
    show([master, *poses], master)
    subjects = {obj.name: obj for obj in master.objects}
    fit = json.loads((BASELINE / "fit-receipt.json").read_text(encoding="utf-8"))
    results = {"method": "Propose–Probe–Compose methodology only", "sleeves": {}}
    edited = ("sweater", "sweater-crouch", "abdomen", "abdomen-crouch", "sleeve-left", "sleeve-right",
              "shoe-left", "shoe-right", "antennae")
    for name in edited:
        obj = subjects[name]
        if name.startswith("sleeve"):
            sign = -1 if name.endswith("left") else 1
            arms = arm_surfaces(obj, poses, "L" if sign == -1 else "R")
            original = tree(obj, Matrix.Identity(4))
            old_mesh = obj.data
            obj.data = fitted_sleeve(obj, arms, sign)
            uniform_uv(obj)
            woven_material(obj, "sweater", palette=SLEEVE_DYES, direction="X", reverse=sign == -1)
            updated = tree(obj, Matrix.Identity(4))
            results["sleeves"][name] = check_sleeve(obj, arms, original, updated)
            for group in poses:
                for piece in group.objects:
                    if piece.data == old_mesh:
                        piece.data = obj.data
            fit[name]["fittedTriangles"] = triangle_count(obj)
            fit[name]["localBlenderBounds"] = [
                [round(extreme(v.co[i] for v in obj.data.vertices), 5) for i in range(3)] for extreme in (min, max)
            ]
        elif name.startswith(("sweater", "abdomen")):
            base = name.split("-")[0]
            obj.data.materials.clear()
            woven_material(obj, base, palette=brighter_palette(base))
        else:
            brighten_shoe_or_antenna(obj)
        export(obj, name)
        print("UPDATED", name, triangle_count(obj), flush=True)
    show([master, *poses], bpy.data.collections["Semibot · stand"])
    scene.cycles.samples = 12
    scene.render.resolution_x, scene.render.resolution_y = 600, 720
    scene.view_settings.view_transform = "Khronos PBR Neutral"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = -.12
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "Bee-Sneaker-Set.blend"))
    (OUTPUT / "fit-receipt.json").write_text(json.dumps(fit, indent=2) + "\n", encoding="utf-8")
    (OUTPUT / "sleeve-check.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    render_all(master, poses, scene, scene.camera, bpy.data.objects["Studio floor"], subjects,
               ("antennae", "sweater", "sleeve-left", "sleeve-right", "abdomen", "wings", "shoe-left", "shoe-right"))


if __name__ == "__main__":
    main()
