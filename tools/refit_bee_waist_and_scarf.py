"""Refit the layered waist on both knit outfits and the New Year Bee scarf."""

import argparse
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_sneaker_release_assets import ITEMS as SNEAKER_ITEMS, VIEWS, export_pack, render_icons
from fit_bee_sneaker_set import show
from fit_new_year_bee import ITEMS as WINTER_ITEMS
from refine_bee_sneaker_fit import tree


def smoothstep(value):
    value = max(0., min(1., value))
    return value * value * (3 - 2 * value)


def fit_scarf(scarf):
    for vertex in scarf.data.vertices:
        point = vertex.co
        direction = Vector((point.x, point.y, 0)).normalized()
        front = smoothstep(-direction.y)
        point.z += .026 * smoothstep((point.z - .265) / .067)
        point += direction * (.019 + .030 * front)
    scarf.data.update()


def tuck_waist(abdomen, sweater, compressed):
    lower = -.013 if compressed else -.113
    lip = .024 if compressed else -.089
    sweater_tree = tree(sweater, Matrix.Identity(4))
    size = 64  # The two authored shells use the same 64-vertex rings.
    vertices = abdomen.data.vertices
    assert len(vertices) % size == 0
    outer_lip = vertices[-2 * size].co.z
    changed_rings = [i for i in range(0, len(vertices) - size, size) if vertices[i].co.z > lower + .001]
    assert changed_rings and changed_rings[-1] == len(vertices) - 2 * size
    for start in changed_rings:
        progress = (vertices[start].co.z - lower) / (outer_lip - lower)
        height = lower + progress * (lip - lower)
        for index in range(start, start + size):
            set_rim_point(vertices[index].co, height, sweater_tree, margin=.013)
    for index in range(len(vertices) - size, len(vertices)):
        set_rim_point(vertices[index].co, lip - .006, sweater_tree, margin=-.017)
    abdomen.data.update()


def set_rim_point(point, height, sweater_tree, margin):
    radial = Vector((point.x, point.y, 0))
    direction = radial.normalized()
    point.z = height
    origin = direction + Vector((0, 0, height))
    distance = sweater_tree.ray_cast(origin, -direction, 1.5)[3]
    assert distance is not None, (height, tuple(point))
    target = 1 - distance + margin
    radius = max(radial.length, target) if margin > 0 else min(radial.length, target)
    point.x, point.y = direction.x * radius, direction.y * radius


def close_underside(abdomen):
    mesh = bmesh.new()
    mesh.from_mesh(abdomen.data)
    mesh.verts.ensure_lookup_table()
    boundary = [mesh.verts[i] for i in range(64)]
    assert all(vert.co.z == boundary[0].co.z for vert in boundary)
    uv = mesh.loops.layers.uv.active
    inner = [mesh.verts.new((vert.co.x * .72, vert.co.y * .72, vert.co.z + .012)) for vert in boundary]
    center = mesh.verts.new((0, 0, boundary[0].co.z + .024))
    for i, outer in enumerate(boundary):
        j = (i + 1) % len(boundary)
        original_edge = mesh.edges.get((outer, boundary[j]))
        assert original_edge.is_boundary
        original_face = original_edge.link_faces[0]
        sample = sum((loop[uv].uv for loop in original_face.loops), Vector((0., 0.))) / len(original_face.loops)
        for corners in ((boundary[j], outer, inner[i], inner[j]), (inner[j], inner[i], center)):
            face = mesh.faces.new(corners)
            face.smooth = True
            for loop in face.loops:
                loop[uv].uv = sample
    mesh.normal_update()
    assert len([edge for edge in mesh.edges if edge.is_boundary]) == 64
    mesh.to_mesh(abdomen.data)
    mesh.free()
    abdomen.data.update()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix", choices=("Sneaker", "Winter"))
    parser.add_argument("blend", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    blend, output = arguments.blend.resolve(), arguments.output.resolve()
    assets, icons = output / "assets", output / "icons"
    assets.mkdir(parents=True, exist_ok=True)
    icons.mkdir(exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    group = bpy.data.collections["Items · anchor local"]
    poses = [col for col in bpy.data.collections if col.name.startswith("Semibot · ")]
    objects = {obj.name: obj for obj in group.objects}
    show([group, *poses], group)
    bpy.context.view_layer.update()
    for suffix in ("", "-crouch"):
        abdomen = objects["abdomen" + suffix]
        tuck_waist(abdomen, objects["sweater" + suffix], compressed=bool(suffix))
        close_underside(abdomen)

    winter = arguments.prefix == "Winter"
    if winter:
        fit_scarf(objects["scarf"])

    show([group, *poses], bpy.data.collections["Semibot · stand"])
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output / blend.name))
    export_pack(objects, assets, items=WINTER_ITEMS if winter else SNEAKER_ITEMS, prefix=arguments.prefix)
    views = {"abdomen": VIEWS["abdomen"]}
    if winter:
        views["scarf"] = (1., -5., 2.1)
    render_icons(group, objects, icons, views=views, prefix=arguments.prefix)


if __name__ == "__main__":
    main()
