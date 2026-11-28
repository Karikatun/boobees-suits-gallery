"""Close fixture-confirmed fabric gaps and make the garment bands continuous."""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_bee_sneaker_set import active, export, render, show, triangle_count, world_bounds


OUTPUT = Path(__file__).resolve().parents[1] / "dist/bee-sneaker-set"
BASELINE = OUTPUT.parents[1] / ".local/bee-sneaker-baseline"
FABRIC = {
    "sweater": [
        (0, (.70, .324, .030)), (.13, (.059, .030, .020)), (.24, (.70, .324, .030)),
        (.30, (.059, .030, .020)), (.328, (.70, .324, .030)), (.94, (.61, .282, .035)),
    ],
    "abdomen": [
        (0, (.58, .233, .022)), (.20, (.055, .029, .020)), (.43, (.68, .307, .027)),
        (.63, (.055, .029, .020)), (.83, (.66, .280, .022)),
    ],
}


def lining(name):
    crouch = name.endswith("-crouch")
    if name.startswith("sweater"):
        lower = -.152 if not crouch else -.012
        seam = (
            [(lower, .312, .336), (lower + .023, .327, .354),
             (-.091, .332, .357), (-.056, .332, .352), (-.028, .324, .340)]
            if not crouch else [(lower, .302, .312), (lower + .023, .310, .319)]
        )
        return seam + [
            (.005 if not crouch else .045, .315, .320),
            (.084, .315, .320), (.144, .317, .325), (.202, .315, .322),
            (.251, .313, .320), (.289, .303, .312), (.318, .294, .304),
            (.338, .284, .292), (.350, .286, .294), (.360, .282, .292),
            (.365, .272, .282), (.361, .262, .271), (.343, .260, .268),
        ]
    if crouch:
        return [
            (-.170, .248, .252), (-.167, .270, .274), (-.154, .299, .302),
            (-.128, .327, .331), (-.093, .347, .352), (-.058, .351, .350),
            (-.013, .340, .343), (.025, .326, .334), (.050, .316, .326),
            (.055, .301, .311), (.048, .293, .305),
        ]
    return [
        (-.402, .243, .251), (-.395, .265, .273), (-.376, .299, .307),
        (-.345, .324, .331), (-.299, .350, .356), (-.248, .365, .371),
        (-.192, .368, .381), (-.151, .364, .376), (-.113, .351, .372),
        (-.084, .338, .363), (-.061, .329, .354), (-.045, .322, .349),
        (-.039, .312, .343), (-.045, .306, .337),
    ]


def tree(obj, transform):
    mesh = obj.data
    mesh.calc_loop_triangles()
    return BVHTree.FromPolygons([transform @ vertex.co for vertex in mesh.vertices],
                               [face.vertices[:] for face in mesh.loop_triangles],
                               all_triangles=True)


def fitted_shell(obj, groups):
    base = obj.name.split("-")[0]
    compressed = obj.name.endswith("-crouch")
    sources = []
    for group in groups:
        if ("crouch" in group.name) != compressed:
            continue
        shell_in_pose = next(part for part in group.objects if part.data == obj.data)
        to_local = shell_in_pose.matrix_world.inverted()
        for part in group.objects:
            if part.name.startswith("player_body"):
                sources.append(tree(part, to_local @ part.matrix_world))
    generated = tree(obj, obj.matrix_world)
    profiles = lining(obj.name)
    if not compressed:
        # At an extreme tilt the top of the lower native panel moves between two
        # authored edges. Sample this overlap more closely instead of stretching
        # the entire silhouette to cover a local gap.
        refined = []
        for low, high in zip(profiles, profiles[1:]):
            steps = math.ceil((high[0] - low[0]) / .009) if -.18 <= low[0] <= .015 else 1
            for i in range(max(1, steps)):
                weight = i / max(1, steps)
                refined.append(tuple(a + weight * (b - a) for a, b in zip(low, high)))
        profiles = [*refined, profiles[-1]]
    segments = 64
    vertices = []
    for ring, (z, rx, ry) in enumerate(profiles):
        for i in range(segments):
            a = i * math.tau / segments
            x, y = math.cos(a), math.sin(a)
            direction = Vector((x, y, 0))
            origin = direction + Vector((0, 0, z))
            reference_radius = 1 / math.hypot(x / rx, y / ry)
            _, _, _, distance = generated.ray_cast(origin, -direction, 1)
            variation = min(.047, max(-.025, 1 - distance - reference_radius)) if distance is not None else 0
            radius = reference_radius + .32 * variation
            if ring < len(profiles) - 2:
                for native in sources:
                    _, _, _, hit = native.ray_cast(origin, -direction, 1)
                    if hit is not None:
                        radius = max(radius, 1 - hit + .016)
            vertices.append((radius * x, radius * y, z))
    faces = []
    for ring in range(len(profiles) - 1):
        for i in range(segments):
            j = (i + 1) % segments
            a, b = ring * segments, (ring + 1) * segments
            faces.append((a + i, a + j, b + j, b + i))
    mesh = bpy.data.meshes.new(obj.name + " · retopologized Meshy shell")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj.data = mesh
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return base


def uniform_uv(obj):
    active(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.20, island_margin=.022, scale_to_bounds=True)
    bpy.ops.object.mode_set(mode="OBJECT")


def woven_material(obj, base, *, palette=None, direction="Z", reverse=False):
    mat = bpy.data.materials.new(obj.name + " · honey textile")
    mat.use_nodes = True
    nodes, lines = mat.node_tree.nodes, mat.node_tree.links
    factory = nodes.new
    shader = nodes.get("Principled BSDF")
    shader.inputs["Roughness"].default_value = .81
    shader.inputs["Sheen Weight"].default_value = .19
    tex = factory("ShaderNodeTexCoord")
    axes = factory("ShaderNodeSeparateXYZ")
    lines.new(tex.outputs["Generated"], axes.inputs[0])
    dyes = factory("ShaderNodeValToRGB")
    dyes.color_ramp.interpolation = "CONSTANT"
    for i, (where, color) in enumerate(palette or FABRIC[base]):
        point = dyes.color_ramp.elements[i] if i < 2 else dyes.color_ramp.elements.new(where)
        point.position, point.color = where, (*color, 1)
    pattern_axis = axes.outputs[direction]
    if reverse:
        flip = factory("ShaderNodeMath")
        flip.operation = "SUBTRACT"
        flip.inputs[0].default_value = 1
        lines.new(pattern_axis, flip.inputs[1])
        pattern_axis = flip.outputs[0]
    lines.new(pattern_axis, dyes.inputs[0])

    noise = factory("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 130 if base == "sweater" else 169
    noise.inputs["Detail"].default_value = 2.0
    noise.inputs["Roughness"].default_value = .72
    lines.new(tex.outputs["Object"], noise.inputs["Vector"])
    woven = factory("ShaderNodeTexWave")
    woven.wave_type = "BANDS"
    woven.bands_direction = direction
    woven.inputs["Scale"].default_value = 94 if base == "sweater" else 40
    woven.inputs["Distortion"].default_value = 1.8
    lines.new(tex.outputs["Object"], woven.inputs["Vector"])
    mix = factory("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = .19 if base == "sweater" else .13
    lines.new(dyes.outputs["Color"], mix.inputs[1])
    lines.new(noise.outputs["Color"], mix.inputs[2])
    bump = factory("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .23 if base == "sweater" else .14
    bump.inputs["Distance"].default_value = .002
    lines.new((woven if base == "sweater" else noise).outputs["Fac"], bump.inputs["Height"])
    lines.new(bump.outputs["Normal"], shader.inputs["Normal"])
    obj.data.materials.append(mat)

    output = nodes.get("Material Output")
    emission = factory("ShaderNodeEmission")
    lines.new(mix.outputs["Color"], emission.inputs["Color"])
    lines.new(emission.outputs[0], output.inputs["Surface"])
    image = bpy.data.images.new(obj.name + "-woven-color", 1024, 1024, alpha=False)
    texture_node = factory("ShaderNodeTexImage")
    texture_node.image = image
    nodes.active = texture_node
    active(obj)
    bpy.context.scene.cycles.samples = 1
    bpy.ops.object.bake(type="EMIT", margin=6, use_clear=True)
    image.pack()
    lines.new(shader.outputs[0], output.inputs["Surface"])
    lines.new(texture_node.outputs["Color"], shader.inputs["Base Color"])
    nodes.remove(emission)


def adjust_sleeve(obj):
    side = -1 if obj.name.endswith("left") else 1
    for v in obj.data.vertices:
        x = side * v.co.x
        hold = max(0, min(1, (.090 - x) / .145))
        v.co.x -= side * .045 * hold
    obj.data.update()


def render_all(master, poses, scene, camera, floor, subjects,
               item_names=("sweater", "abdomen", "sleeve-left", "sleeve-right", "shoe-left")):
    preview = bpy.data.collections.new("Isolated item preview")
    scene.collection.children.link(preview)
    master.hide_render = master.hide_viewport = True
    for name in item_names:
        obj = subjects[name].copy()
        preview.objects.link(obj)
        show([*poses, preview], preview)
        bpy.context.view_layer.update()
        lo, hi = world_bounds([obj])
        target = (lo + hi) * .5
        floor.location = (target.x, target.y, lo.z - .016)
        direction = (-2.7, -4.8, 1.4) if name == "shoe-left" else (2.2, -4.8, 1.4)
        if name == "wings":
            direction = (1.1, 4.8, 1.2)
        render(scene, camera, target, direction, 1.30 * max(hi - lo), (460, 460), name)
        bpy.data.objects.remove(obj, do_unlink=True)
    for group in poses:
        tag = group.name.split(" · ")[1]
        show([*poses, preview], group)
        bpy.context.view_layer.update()
        lo, hi = world_bounds(list(group.objects))
        floor.location = (0, 0, lo.z - .007)
        target = Vector((0, (lo.y + hi.y) * .5, .5 * (lo.z + hi.z)))
        scale = max(1.26 * (hi.z - lo.z), 1.6)
        views = {"front": (0, -5, .30), "three-quarter": (2.7, -5, .58)}
        if tag in {"stand", "crouch"}:
            views["rear"] = (2.5, 5, .65)
        for view, direction in views.items():
            render(scene, camera, target, direction, scale, (500, 620), f"{tag}-{view}")


def main():
    bpy.ops.wm.open_mainfile(filepath=str(BASELINE / "Bee-Sneaker-Set.blend"))
    scene = bpy.context.scene
    master = bpy.data.collections["Items · anchor local"]
    poses = [col for col in bpy.data.collections if col.name.startswith("Semibot · ")]
    show([master, *poses], master)
    subjects = {obj.name: obj for obj in master.objects}
    stats = json.loads((BASELINE / "fit-receipt.json").read_text(encoding="utf-8"))
    for name in ("sweater", "sweater-crouch", "abdomen", "abdomen-crouch",
                 "sleeve-left", "sleeve-right"):
        obj = subjects[name]
        old = obj.data
        if name.startswith("sleeve"):
            obj.data = old.copy()
            adjust_sleeve(obj)
        else:
            base = fitted_shell(obj, poses)
            uniform_uv(obj)
            woven_material(obj, base)
        for group in poses:
            for part in group.objects:
                if part.data == old:
                    part.data = obj.data
        export(obj, name)
        canonical = name.removesuffix("-crouch")
        field = "crouchTriangles" if name.endswith("-crouch") else "fittedTriangles"
        stats[canonical][field] = triangle_count(obj)
        if field == "fittedTriangles":
            stats[canonical]["localBlenderBounds"] = [
                [round(extreme(v.co[i] for v in obj.data.vertices), 5) for i in range(3)]
                for extreme in (min, max)
            ]
        print("REFINED", name, stats[canonical][field], flush=True)
    show([master, *poses], bpy.data.collections["Semibot · stand"])
    scene.cycles.samples = 12
    scene.render.resolution_x, scene.render.resolution_y = 600, 720
    camera, floor = scene.camera, bpy.data.objects["Studio floor"]
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "Bee-Sneaker-Set.blend"))
    (OUTPUT / "fit-receipt.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    render_all(master, poses, scene, camera, floor, subjects)


if __name__ == "__main__":
    main()
