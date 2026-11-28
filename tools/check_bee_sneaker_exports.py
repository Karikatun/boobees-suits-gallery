"""Reimport the staged cosmetic FBX files and verify that their meshes survived export."""

import hashlib
import json
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


OUTPUT = Path(__file__).resolve().parents[1] / "dist/bee-sneaker-set"


def tree(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    return BVHTree.FromPolygons([obj.matrix_world @ v.co for v in mesh.vertices],
                                [f.vertices[:] for f in mesh.loop_triangles], all_triangles=True)


def sample_front(item, native, garment, levels):
    matrix = item.matrix_world
    direction = (matrix.to_3x3() @ Vector((0, 1, 0))).normalized()
    tested = exposed = 0
    for z in levels:
        for x in (-.20, -.12, -.06, 0., .06, .12, .20):
            start = matrix @ Vector((x, -1, z))
            skin = [dist for _, _, _, dist in (model.ray_cast(start, direction) for model in native)
                    if dist is not None]
            if skin:
                tested += 1
                cloth = [dist for _, _, _, dist in (model.ray_cast(start, direction) for model in garment)
                         if dist is not None]
                exposed += not cloth or min(cloth) > min(skin) + .003
    return {"testedRays": tested, "exposedRays": exposed}


def validate_pose_scene(names):
    bpy.ops.wm.open_mainfile(filepath=str(OUTPUT / "Bee-Sneaker-Set.blend"))
    poses = {}
    for label in ("stand", "crouch", "stand-down", "stand-up", "crouch-down", "crouch-up"):
        group = bpy.data.collections[f"Semibot · {label}"]
        by_id = {obj.name.split(".")[0].removesuffix("-crouch"): obj for obj in group.objects}
        assert all(item in by_id for item in names), label
        assert all(eye in by_id for eye in ("player_eye_L", "player_eye_R")), label
        assert all(obj.matrix_world.determinant() > .000001 for key, obj in by_id.items() if key in names), label
        body = [tree(obj) for key, obj in by_id.items() if key.startswith("player_body")]
        legs = [tree(obj) for key, obj in by_id.items() if key.startswith("player_leg")]
        top = by_id["sweater"]
        bottom = by_id["abdomen"]
        outfit = [tree(top), tree(bottom)]
        compression = label.startswith("crouch")
        poses[label] = {
            "items": len(names),
            "sweaterCenter": sample_front(top, body, outfit, (.03, .08, .13, .18, .23)),
            "abdomenCenter": sample_front(bottom, [*body, *legs], outfit,
                                          (-.16, -.12, -.08, -.05) if compression else (-.29, -.24, -.19, -.14)),
        }
    return poses


def validate_file(name, expected):
    file = OUTPUT / "items" / (name + ".fbx")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(file), use_image_search=False)
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    assert len(meshes) == 1, name
    mesh = meshes[0].data
    mesh.calc_loop_triangles()
    assert len(mesh.loop_triangles) == expected, name
    assert mesh.uv_layers.active is not None, name
    assert len(mesh.materials) > 0, name
    textures = [node.image for mat in mesh.materials if mat and mat.use_nodes
                for node in mat.node_tree.nodes if node.type == "TEX_IMAGE" and node.image]
    assert textures and any(image.has_data for image in textures), name
    return {"triangles": len(mesh.loop_triangles), "vertices": len(mesh.vertices),
            "uvLayers": len(mesh.uv_layers), "materials": len(mesh.materials),
            "loadedTextures": sum(image.has_data for image in textures),
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}


def main():
    fit = json.loads((OUTPUT / "fit-receipt.json").read_text(encoding="utf-8"))
    poses = validate_pose_scene(fit)
    (OUTPUT / "pose-check.json").write_text(json.dumps(poses, indent=2) + "\n", encoding="utf-8")
    print("POSE_CHECK", json.dumps(poses), flush=True)
    result = {}
    for name, stats in fit.items():
        result[name] = validate_file(name, stats["fittedTriangles"])
        if stats["crouchTriangles"] is not None:
            result[name + "-crouch"] = validate_file(name + "-crouch", stats["crouchTriangles"])
    (OUTPUT / "export-check.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("Checked FBX round trip, triangle counts and UVs", len(result))


if __name__ == "__main__":
    main()
