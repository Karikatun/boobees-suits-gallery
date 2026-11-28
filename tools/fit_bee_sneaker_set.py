"""Fit the eight Meshy bee accessories to the recorded native Semibot poses."""

import csv
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist/bee-sneaker-set"
MESHY = OUTPUT / "meshy"
RIG = ROOT / ".local/semibot-preview/semibot-native.json"
CAPTURE = ROOT / ".local/cosmetic-skills/game/item-regions/matrices.tsv"
BASIS = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
ITEMS = {
    "antennae": ("Hat", 900),
    "sweater": ("BodyTop", 3200),
    "sleeve-left": ("ArmLeft", 1400),
    "sleeve-right": ("ArmRight", 1400),
    "abdomen": ("BodyTopOverlay", 2600),
    "wings": ("BodyTop", 2200),
    "shoe-left": ("FootLeft", 5200),
    "shoe-right": ("FootRight", 5200),
}
POSES = {
    "stand": "stand/0", "crouch": "crouch/0",
    "stand-down": "stand/85", "stand-up": "stand/-75",
    "crouch-down": "crouch/55", "crouch-up": "crouch/-55",
}


def collection(name):
    group = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(group)
    return group


def in_collection(obj, group):
    for previous in tuple(obj.users_collection):
        previous.objects.unlink(obj)
    group.objects.link(obj)


def material(name, color, roughness, metal=0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, 1.0)
    node = mat.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value = (*color, 1)
    node.inputs["Roughness"].default_value = roughness
    node.inputs["Metallic"].default_value = metal
    return mat


def active(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def coords(obj):
    values = np.empty(len(obj.data.vertices) * 3, dtype=np.float32)
    obj.data.vertices.foreach_get("co", values)
    return values.reshape(-1, 3).astype(float)


def triangle_count(obj):
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def load_model(item):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(MESHY / f"{item}.glb"), merge_vertices=True)
    loaded = set(bpy.data.objects) - before
    meshes = sorted((obj for obj in loaded if obj.type == "MESH"), key=lambda obj: obj.name)
    extras = [obj for obj in loaded if obj.type != "MESH"]
    if not meshes:
        raise ValueError(f"{item}: no geometry")
    for obj in meshes:
        world = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = world
    active(meshes[0])
    for obj in meshes[1:]:
        obj.select_set(True)
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.object
    obj.data.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)
    for node in extras:
        bpy.data.objects.remove(node, do_unlink=True)
    obj.name = item
    return obj


def decimate(obj, budget):
    for _ in range(3):
        count = triangle_count(obj)
        if count <= budget:
            break
        active(obj)
        mod = obj.modifiers.new("Triangle budget", "DECIMATE")
        mod.ratio = min(.999, budget * .985 / count)
        bpy.ops.object.modifier_apply(modifier=mod.name)
    assert triangle_count(obj) <= budget, (obj.name, triangle_count(obj), budget)


def weld_surface(obj):
    active(obj)
    if obj.data.has_custom_normals:
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    # Meshy/glTF can split vertices by texture charts, even when the physical
    # surface is continuous. Keep UVs on the loops and weld only coincident positions.
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.000012)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    for face in obj.data.polygons:
        face.use_smooth = True
    obj.data.update()


def fit_axis(values, new_lo, new_hi):
    lo, hi = values.min(), values.max()
    assert hi - lo > .00001, (lo, hi)
    return new_lo + (new_hi - new_lo) * (values - lo) / (hi - lo)


def fit_box(p, lo, hi):
    return np.column_stack([fit_axis(p[:, i], lo[i], hi[i]) for i in range(3)])


def normalized(a):
    return a / np.linalg.norm(a)


def sleeve(p, side):
    centered = p - p.mean(axis=0)
    _u, _s, axes = np.linalg.svd(centered, full_matrices=False)
    lengthwise = axes[0]
    axial = centered @ lengthwise
    radii = np.linalg.norm(centered - axial[:, None] * lengthwise, axis=1)
    upper = axial >= np.quantile(axial, .84)
    lower = axial <= np.quantile(axial, .16)
    if np.quantile(radii[upper], .8) > np.quantile(radii[lower], .8):
        lengthwise *= -1
    up = normalized(np.array([0.0, 0.0, 1.0]) - lengthwise * lengthwise[2])
    across = np.cross(up, lengthwise)
    # Keep a positive determinant when converting to the negative left arm axis.
    aligned = centered @ np.column_stack((lengthwise, across, up))
    axial = fit_axis(aligned[:, 0], -.055, .538)
    centers = []
    sizes = []
    data = aligned[:, 1:]
    for x in np.linspace(-.055, .538, 40):
        indices = np.argsort(abs(axial - x))[:max(30, len(axial) // 50)]
        ring = data[indices]
        c = .5 * (ring.min(axis=0) + ring.max(axis=0))
        centers.append(c)
        sizes.append(max(np.quantile(np.linalg.norm(ring - c, axis=1), .86), .002))
    levels = np.linspace(-.055, .538, 40)
    center = np.column_stack([np.interp(axial, levels, np.array(centers)[:, i]) for i in range(2)])
    radial = (data - center) / np.interp(axial, levels, sizes)[:, None]
    shape = np.interp(axial, [-.055, -.020, .02, .15, .30, .45, .50, .529, .538],
                      [.065, .084, .084, .070, .055, .041, .033, .024, .013])
    cross = radial * shape[:, None]
    return np.column_stack((side * axial, side * cross[:, 0], cross[:, 1]))


def sneaker(p):
    xy = p[:, :2] - p[:, :2].mean(axis=0)
    _u, _s, axes = np.linalg.svd(xy, full_matrices=False)
    forward = axes[0]
    signed = xy @ forward
    low = p[signed < np.quantile(signed, .22), 2]
    high = p[signed > np.quantile(signed, .78), 2]
    # The ankle and upper have greater height than the toe box.
    if np.quantile(high, .88) > np.quantile(low, .88):
        forward *= -1
    right = np.array([-forward[1], forward[0]])
    q = np.column_stack((xy @ right, -(xy @ forward), p[:, 2]))
    return fit_box(q, (-.088, -.169, -.564), (.088, .079, -.359))


def antennae(p):
    out = np.empty_like(p)
    center = (p[:, 0].max() + p[:, 0].min()) / 2
    for side in (-1, 1):
        rows = (p[:, 0] - center) * side > 0
        points = p[rows]
        foot = points[points[:, 2] <= np.quantile(points[:, 2], .12)]
        base = np.median(foot[:, 0])
        reach = max(abs(points[:, 0] - base).max(), .001)
        out[rows, 0] = side * .104 + (points[:, 0] - base) * .126 / reach
        out[rows, 1] = fit_axis(points[:, 1], -.314, -.271)
        out[rows, 2] = fit_axis(points[:, 2], .340, .584)
    return out


def fitted_positions(name, p, compressed=False):
    if name.startswith("sleeve"):
        return sleeve(p, -1 if name.endswith("left") else 1)
    if name.startswith("shoe"):
        return sneaker(p)
    if name == "antennae":
        return antennae(p)
    if name == "sweater":
        return fit_box(p, (-.332, -.340, .004 if compressed else -.140),
                       (.332, .316, .325))
    if name == "abdomen":
        return fit_box(p, (-.359, -.356, -.191 if compressed else -.416),
                       (.359, .395, .088 if compressed else -.080))
    if name == "wings":
        result = fit_box(p, (-.506, .222, .032), (.506, .295, .394))
        # Lift the wing tips away from the back while keeping both roots close.
        swept = np.clip((abs(result[:, 0]) - .15) / .36, 0, 1)
        result[:, 1] += swept * .10
        return result
    raise ValueError(name)


def set_positions(obj, positions):
    assert np.isfinite(positions).all(), obj.name
    obj.data.vertices.foreach_set("co", np.asarray(positions, dtype=np.float32).ravel())
    obj.data.update()


def export(obj, name):
    active(obj)
    bpy.ops.export_scene.fbx(filepath=str(OUTPUT / "items" / f"{name}.fbx"),
                             use_selection=True, object_types={"MESH"},
                             add_leaf_bones=False, path_mode="COPY", embed_textures=True)


def capture():
    desired = set(POSES.values())
    results = {pose: {} for pose in desired}
    with CAPTURE.open(newline="", encoding="utf-8") as file:
        for kind, method, pose, t, name, visible, *cells in csv.reader(file, delimiter="\t"):
            if method != "runtime-aim" or pose not in desired or visible != "1":
                continue
            results[pose].setdefault(float(t), {})[kind, name] = BASIS @ Matrix(
                [tuple(map(float, cells[i:i + 4])) for i in range(0, 12, 4)] + [(0, 0, 0, 1)]
            ) @ BASIS.inverted()
    return {pose: rows[sorted(rows)[len(rows) // 2]] for pose, rows in results.items()}


def native_data():
    meshes = {}
    for row in json.loads(RIG.read_text(encoding="utf-8"))["meshes"]:
        meshes.setdefault(row["name"], row)
    return meshes


def stock(name, row, group, mats):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(x, -z, y) for x, y, z in row["verts"]], [], row["triangles"])
    mesh.update()
    for face in mesh.polygons:
        face.use_smooth = True
    if name.startswith("player_iris"):
        mat = mats["iris"]
    elif name.startswith("player_eye"):
        mat = mats["eye"]
    elif name.startswith(("player_leg", "player_arm", "player_head_bot")):
        mat = mats["limb"]
    elif name == "player_health_LED":
        mat = mats["led"]
    else:
        mat = mats["body"]
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    group.objects.link(obj)
    return obj


def studio():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 12
    scene.cycles.use_denoising = True
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = .35
    scene.world = bpy.data.worlds.new("Neutral studio")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (.29, .28, .25, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = .34
    bpy.ops.mesh.primitive_plane_add(size=200)
    floor = bpy.context.object
    floor.name = "Studio floor"
    floor.data.materials.append(material("Slate floor", (.070, .092, .103), .85))
    for pos, power, size, color in (
        ((-3.5, -4.1, 4.3), 700, 4.0, (1, .87, .68)),
        ((3.7, -2.2, 2.6), 325, 3.0, (.78, .90, 1)),
        ((1.0, 3.0, 4.1), 650, 2.8, (1, .89, .73)),
    ):
        bpy.ops.object.light_add(type="AREA", location=pos)
        light = bpy.context.object
        light.data.energy, light.data.size, light.data.color = power, size, color
        light.rotation_euler = (Vector((0, 0, 1)) - light.location).to_track_quat("-Z", "Y").to_euler()
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    scene.camera = camera
    return scene, camera, floor


def show(groups, target):
    for group in groups:
        group.hide_render = group != target
        group.hide_viewport = group != target


def world_bounds(objects):
    corners = np.array([tuple(obj.matrix_world @ Vector(v)) for obj in objects for v in obj.bound_box])
    return Vector(corners.min(axis=0)), Vector(corners.max(axis=0))


def render(scene, camera, target, direction, scale, size, filename):
    camera.location = target + Vector(direction).normalized() * 4.0
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.ortho_scale = scale
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.filepath = str(OUTPUT / "renders" / f"{filename}.png")
    bpy.ops.render.render(write_still=True)


def main():
    global OUTPUT
    probe = "--partial-probe" in sys.argv
    if probe:
        OUTPUT = ROOT / ".local/bee-sneaker-fit-probe"
        for folder in (OUTPUT / "items", OUTPUT / "renders"):
            folder.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    master = collection("Items · anchor local")
    subjects, variants, receipt = {}, {}, {}
    for name, (slot, budget) in ITEMS.items():
        if probe and not (MESHY / f"{name}.glb").is_file():
            continue
        obj = load_model(name)
        in_collection(obj, master)
        before = triangle_count(obj)
        weld_surface(obj)
        # Fit each pose variant before reduction so simplification uses final proportions.
        p = coords(obj)
        if name in ("sweater", "abdomen"):
            other = obj.copy()
            other.data = obj.data.copy()
            other.name = f"{name}-crouch"
            master.objects.link(other)
            set_positions(other, fitted_positions(name, p, True))
            decimate(other, budget)
            variants[name] = other
        set_positions(obj, fitted_positions(name, p))
        decimate(obj, budget)
        subjects[name] = obj
        receipt[name] = {"slot": slot, "meshyTriangles": before, "fittedTriangles": triangle_count(obj),
                         "localBlenderBounds": np.round([coords(obj).min(axis=0), coords(obj).max(axis=0)], 5).tolist(),
                         "crouchTriangles": triangle_count(variants[name]) if name in variants else None,
                         "materialCount": len(obj.data.materials)}
    for obj in [*subjects.values(), *variants.values()]:
        export(obj, obj.name)
    bpy.ops.file.pack_all()
    master.hide_render = master.hide_viewport = True

    rig = native_data()
    frames = capture()
    mats = {
        "eye": material("Stock eye", (.72, .81, .86), .23),
        "iris": material("Stock pupil", (.025, .041, .051), .25),
        "body": material("Stock cool steel", (.225, .305, .348), .32, .58),
        "limb": material("Stock dark steel", (.105, .153, .18), .36, .55),
        "led": material("Stock health LED", (.08, .25, .16), .42),
    }
    pose_groups = {}
    pose_members = {}
    for tag, sample in POSES.items():
        group = pose_groups[tag] = collection(f"Semibot · {tag}")
        frame = frames[sample]
        members = []
        for (kind, name), matrix in frame.items():
            if kind == "mesh" and name in rig and "grabber" not in name:
                obj = stock(name, rig[name], group, mats)
                obj.matrix_world = matrix
                members.append(obj)
        for name in subjects:
            slot = ITEMS[name][0]
            source = variants.get(name, subjects[name]) if tag.startswith("crouch") else subjects[name]
            obj = source.copy()
            group.objects.link(obj)
            obj.matrix_world = frame["slot", slot]
            members.append(obj)
        pose_members[tag] = members

    scene, camera, floor = studio()
    if probe:
        scene.cycles.samples = 5
    show(pose_groups.values(), pose_groups["stand"])
    bpy.context.view_layer.update()
    lo, hi = world_bounds(pose_members["stand"])
    floor.location.z = lo.z - .007
    camera.location = (2.2, -4.8, 2.05)
    camera.rotation_euler = (.5 * (lo + hi) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.ortho_scale = 2.25
    scene.render.resolution_x, scene.render.resolution_y = 600, 720
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "Bee-Sneaker-Set.blend"))
    (OUTPUT / "fit-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print("FIT_RECEIPT", json.dumps(receipt), flush=True)

    standalone = collection("Isolated item")
    for name, asset in subjects.items():
        obj = asset.copy()
        standalone.objects.link(obj)
        show([*pose_groups.values(), standalone], standalone)
        bpy.context.view_layer.update()
        lo, hi = world_bounds([obj])
        target = (lo + hi) * .5
        floor.location = (target.x, target.y, lo.z - .016)
        direction = (2.2, -4.8, 1.4)
        if name == "wings":
            direction = (1.1, 4.8, 1.2)
        render(scene, camera, target, direction, 1.30 * max(hi - lo), (460, 460), name)
        bpy.data.objects.remove(obj, do_unlink=True)

    for tag, group in pose_groups.items():
        if probe and tag not in {"stand", "crouch-down"}:
            continue
        show([*pose_groups.values(), standalone], group)
        bpy.context.view_layer.update()
        lo, hi = world_bounds(pose_members[tag])
        floor.location = (0, 0, lo.z - .007)
        target = Vector((0, (lo.y + hi.y) * .5, .5 * (lo.z + hi.z)))
        height = hi.z - lo.z
        scale = max(1.26 * height, 1.6)
        views = {"front": (0, -5, .30), "three-quarter": (2.7, -5, .58)}
        if tag in {"stand", "crouch"}:
            views["rear"] = (2.5, 5, .65)
        for view, direction in views.items():
            render(scene, camera, target, direction, scale,
                   (360, 446) if probe else (500, 620), f"{tag}-{view}")


if __name__ == "__main__":
    main()
