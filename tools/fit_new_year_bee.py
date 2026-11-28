"""Fit the nine New Year Bee items from Meshy and render native captured poses."""

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_bee_sneaker_set as fit
from refine_bee_sneaker_fit import render_all, tree


OUTPUT = Path(__file__).resolve().parents[1] / "dist/new-year-bee"
PLACEMENT = fit.OUTPUT / "Bee-Sneaker-Set.blend"
ITEMS = {
    "hat": ("Hat", 2800),
    "scarf": ("BodyTop", 1800),
    "sweater": ("BodyTop", 5500),
    "sleeve-left": ("ArmLeft", 1800),
    "sleeve-right": ("ArmRight", 1800),
    "abdomen": ("BodyTopOverlay", 3300),
    "wings": ("BodyTop", 2800),
    "boot-left": ("FootLeft", 3800),
    "boot-right": ("FootRight", 3800),
}
STATIC = {"hat", "scarf", "wings", "boot-left", "boot-right"}


def remove_duplicate_faces(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    mesh.verts.index_update()
    seen, duplicates = set(), []
    for face in mesh.faces:
        corners = tuple(sorted(vertex.index for vertex in face.verts))
        if corners in seen:
            duplicates.append(face)
        seen.add(corners)
    if duplicates:
        bmesh.ops.delete(mesh, geom=duplicates, context="FACES_ONLY")
        mesh.to_mesh(obj.data)
        obj.data.update()
    mesh.free()
    return len(duplicates)


def compress_hat_height(obj):
    positions = fit.coords(obj)
    positions[:, 2] -= .31 * np.maximum(positions[:, 2] - .285, 0)
    fit.set_positions(obj, positions)


def normalized_source(name, vertices):
    if name == "hat":
        q = fit.fit_box(vertices, (-.319, -.519, .228), (.319, .011, .682))
        rim = q[q[:, 2] < .285]
        center = (np.quantile(rim[:, :2], .93, axis=0) + np.quantile(rim[:, :2], .07, axis=0)) * .5
        q[:, :2] += np.array([0., -.254]) - center
        return q
    if name == "scarf":
        # Let the knit follow the sweater collar as the head pivots above it.
        return fit.fit_box(vertices, (-.292, -.388, .201), (.292, .317, .404))
    if name.startswith("boot"):
        q = fit.sneaker(vertices)
        return fit.fit_box(q, (-.091, -.176, -.565), (.091, .081, -.344))
    return fit.fitted_positions("wings", vertices)


def assign_cylindrical_uv(obj, name):
    sleeve = name.startswith("sleeve")
    side = -1 if name.endswith("left") else 1
    axis = 0 if sleeve else 2
    coordinates = fit.coords(obj)
    height = coordinates[:, axis] * (side if sleeve else 1)
    height = fit.fit_axis(height, 0., 1.)
    if sleeve:
        across = (np.arctan2(coordinates[:, 1], coordinates[:, 2]) / math.tau + .5) % 1
    else:
        across = (np.arctan2(coordinates[:, 1], coordinates[:, 0]) / math.tau + .75) % 1
    for old in tuple(obj.data.uv_layers):
        obj.data.uv_layers.remove(old)
    layer = obj.data.uv_layers.new(name="Knit")
    for polygon in obj.data.polygons:
        verts = [obj.data.loops[i].vertex_index for i in polygon.loop_indices]
        uses_wrap = max(across[x] for x in verts) - min(across[x] for x in verts) > .5
        for loop, vertex in zip(polygon.loop_indices, verts):
            u = across[vertex]
            layer.data[loop].uv = (u + 1 if uses_wrap and u < .5 else u, height[vertex])


def yarn_material(obj, name):
    kind = "sleeve" if name.startswith("sleeve") else name.removesuffix("-crouch")
    mat = fit.material(name + " · winter knit", (.045, .13, .08), .83)
    nodes, edges = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Sheen Weight"].default_value = .20
    image_node = nodes.new("ShaderNodeTexImage")
    image_node.image = bpy.data.images.load(str(OUTPUT / "textures" / f"{kind}.png"), check_existing=True)
    image_node.extension = "REPEAT"
    edges.new(image_node.outputs["Color"], shader.inputs["Base Color"])
    thread = nodes.new("ShaderNodeTexNoise")
    thread.inputs["Scale"].default_value = 220
    thread.inputs["Detail"].default_value = 2.0
    coords = nodes.new("ShaderNodeTexCoord")
    edges.new(coords.outputs["Object"], thread.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .16
    bump.inputs["Distance"].default_value = .0016
    edges.new(thread.outputs["Fac"], bump.inputs["Height"])
    edges.new(bump.outputs[0], shader.inputs["Normal"])
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def model_from_source(raw, template, name, master):
    obj = bpy.data.objects.new(name, template.data.copy())
    master.objects.link(obj)
    if name.startswith("sleeve"):
        sign = -1 if name.endswith("left") else 1
        fit.set_positions(raw, fit.sleeve(fit.coords(raw), sign))
        axis, ring = 0, (1, 2)
    else:
        source = fit.coords(raw)
        garment = fit.coords(template)
        fit.set_positions(raw, fit.fit_box(source, garment.min(axis=0), garment.max(axis=0)))
        axis, ring = 2, (0, 1)
    bvh = tree(raw, Matrix.Identity(4))
    max_offset = .007 if name.startswith("sleeve") else .012
    for vertex in obj.data.vertices:
        p = vertex.co
        line = p.copy()
        line[ring[0]] = line[ring[1]] = 0
        vector = p - line
        radius = vector.length
        if radius <= .005:
            continue
        normal = vector / radius
        _, _, _, hit = bvh.ray_cast(line + normal, -normal, 1)
        if hit is not None:
            # Hold the clearance from the native rig while carrying the sampled wool silhouette.
            offset = max(0., min(max_offset, (1 - hit - radius) * .30))
            p += normal * offset
    obj.data.update()
    assign_cylindrical_uv(obj, name)
    yarn_material(obj, name)
    return obj


def add_hat_glow(obj):
    mat = obj.data.materials[0]
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    original = shader.inputs["Base Color"].links[0].from_node.image
    pixels = np.empty(len(original.pixels), dtype=np.float32)
    original.pixels.foreach_get(pixels)
    pixels = pixels.reshape(-1, 4)
    r, g, b = (pixels[:, i] for i in range(3))
    mask = np.clip((g - .36) / .20, 0, 1)
    mask *= np.clip((g / np.maximum(r, .001) - .41) / .20, 0, 1)
    mask *= np.clip((g - b - .16) / .22, 0, 1)
    glow = np.column_stack((mask, mask * .53, mask * .14, np.ones_like(mask)))
    emission = bpy.data.images.new("Winter hat amber emission", *original.size, alpha=False)
    emission.colorspace_settings.name = "Non-Color"
    emission.pixels.foreach_set(np.ascontiguousarray(glow.ravel(), dtype=np.float32))
    emission.update()
    emission.pack()
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = emission
    links.new(tex.outputs["Color"], shader.inputs["Emission Color"])
    shader.inputs["Emission Strength"].default_value = 1.25
    return int(np.count_nonzero(mask > .20))


def main():
    bpy.ops.wm.open_mainfile(filepath=str(PLACEMENT))
    fit.OUTPUT, fit.MESHY = OUTPUT, OUTPUT / "meshy"
    scene = bpy.context.scene
    master = bpy.data.collections["Items · anchor local"]
    poses = [g for g in bpy.data.collections if g.name.startswith("Semibot · ")]
    fit.show([master, *poses], master)
    originals = {obj.name: obj for obj in master.objects}
    sources_for = {name: mesh.data for name, mesh in originals.items()}
    original_data = set(sources_for.values())
    model, fit_stats = {}, {}
    for name, (slot, budget) in ITEMS.items():
        raw = fit.load_model(name)
        before = fit.triangle_count(raw)
        fit.weld_surface(raw)
        duplicate_faces = 0
        if name in STATIC:
            fit.in_collection(raw, master)
            fit.set_positions(raw, normalized_source(name, fit.coords(raw)))
            fit.decimate(raw, budget)
            duplicate_faces = remove_duplicate_faces(raw)
            if name == "hat":
                compress_hat_height(raw)
            model[name] = raw
        else:
            # Preserve the source posed shapes before normalizing the Meshy candidate.
            sources = [originals[name]]
            if name + "-crouch" in originals:
                sources.append(originals[name + "-crouch"])
            raw_orig = raw.data.copy() if len(sources) > 1 else None
            raw.name = name + " · Meshy source"
            for i, source in enumerate(sources):
                if i:
                    raw.data = raw_orig
                suffix = "-crouch" if i else ""
                model[name + suffix] = model_from_source(raw, source, name + suffix, master)
            bpy.data.objects.remove(raw, do_unlink=True)
        mesh = model[name]
        fit_stats[name] = {
            "slot": slot, "meshyTriangles": before, "fittedTriangles": fit.triangle_count(mesh),
            "removedDuplicateFaces": duplicate_faces,
            "crouchTriangles": fit.triangle_count(model[name + "-crouch"]) if name + "-crouch" in model else None,
            "localBlenderBounds": np.round([fit.coords(mesh).min(axis=0), fit.coords(mesh).max(axis=0)], 5).tolist(),
        }
        if name == "hat":
            fit_stats[name]["emissivePixels"] = add_hat_glow(mesh)
        print("WINTER_FIT", name, fit_stats[name], flush=True)

    # Remove the old clothing instances after all placement constraints have been used.
    for group in poses:
        for obj in list(group.objects):
            if obj.data in original_data:
                bpy.data.objects.remove(obj, do_unlink=True)
    for obj in originals.values():
        bpy.data.objects.remove(obj, do_unlink=True)

    frames = fit.capture()
    for group in poses:
        tag = group.name.split(" · ")[1]
        frame = frames[fit.POSES[tag]]
        for name, (slot, _) in ITEMS.items():
            variant = name + "-crouch"
            source = model[variant] if tag.startswith("crouch") and variant in model else model[name]
            obj = source.copy()
            group.objects.link(obj)
            obj.matrix_world = frame["slot", slot]

    for key, obj in model.items():
        obj.name = key
        fit.export(obj, key)
    fit.show([master, *poses], bpy.data.collections["Semibot · stand"])
    scene.cycles.samples = 12
    scene.view_settings.view_transform = "Khronos PBR Neutral"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = -.12
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "New-Year-Bee.blend"))
    (OUTPUT / "fit-receipt.json").write_text(json.dumps(fit_stats, indent=2) + "\n", encoding="utf-8")
    render_all(master, poses, scene, scene.camera, bpy.data.objects["Studio floor"], model, tuple(ITEMS))


if __name__ == "__main__":
    main()
