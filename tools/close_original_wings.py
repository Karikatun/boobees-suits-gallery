"""Repair open cuts in the original fitted wing pair and retain its fabric atlas."""

import json
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform, intersect_point_line

WELD = .000024


def stitch_cut_edges(bm):
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=WELD)
    boundary = [edge for edge in bm.edges if edge.is_boundary]
    tips = {v for edge in boundary for v in edge.verts}
    for edge in boundary:
        a, b = edge.verts
        length = edge.calc_length()
        if length <= 2 * WELD:
            continue
        fractions = []
        for tip in tips - {a, b}:
            hit, fraction = intersect_point_line(tip.co, a.co, b.co)
            if WELD < fraction * length < length - WELD and (hit - tip.co).length < WELD:
                fractions.append(fraction)
        previous = 0.
        for fraction in sorted(fractions):
            if (fraction - previous) * length <= WELD:
                continue
            _, a = bmesh.utils.edge_split(edge, a, (fraction - previous) / (1 - previous))
            edge = next(candidate for candidate in a.link_edges if b in candidate.verts)
            previous = fraction
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=WELD)


def fabric_donors(mesh):
    mesh.calc_loop_triangles()
    points = [v.co for v in mesh.vertices]
    triangles = [t.vertices[:] for t in mesh.loop_triangles]
    tree = BVHTree.FromPolygons(points, triangles, all_triangles=True)
    color = next(node.image for node in mesh.materials[0].node_tree.nodes
                 if node.type == 'TEX_IMAGE' and node.image.name.startswith('color.png'))
    width, height = color.size
    data = np.empty(width * height * 4, dtype='f')
    color.pixels.foreach_get(data)
    data = data.reshape((height, width, 4))[:, :, :3]
    sample_radius = max(5, round(min(width, height) * .020))
    uv = mesh.uv_layers.active.data
    lo, hi = min(v.z for v in points), max(v.z for v in points)
    donors = {}
    for side in (-1, 1):
        candidates = []
        for x in (.326, .345, .364, .382, .397, .414):
            for t in (.55, .61, .67, .73, .79, .85):
                origin = Vector((side * x, 1., lo + (hi - lo) * t))
                hit, _, index, _ = tree.ray_cast(origin, Vector((0., -1., 0.)), 1.)
                if hit is None:
                    continue
                tri = mesh.loop_triangles[index]
                donor = barycentric_transform(hit, *(points[v] for v in tri.vertices),
                                              *(uv[k].uv.to_3d() for k in tri.loops))
                u, v = round(donor.x * width), round(donor.y * height)
                patch = data[v-sample_radius:v+sample_radius+1, u-sample_radius:u+sample_radius+1]
                if patch.shape[:2] != (2 * sample_radius + 1,) * 2:
                    continue
                candidates.append((donor.to_2d(), patch.mean(axis=(0, 1)), float(patch.std(axis=(0, 1)).mean())))
        assert candidates, 'No fabric samples on the original wing'
        target = np.median([mean for _, mean, _ in candidates], axis=0)
        donors[side], _, _ = min(candidates, key=lambda c: float(np.linalg.norm(c[1] - target)) + c[2] * 2.)
    return donors


def sew_cap(bm, cap):
    rim = list(cap.verts)
    if len(rim) == 3:
        return [cap]

    # Give cap diagonals their own vertices. The scan already has some of the
    # same chords on the opposite skin, so reusing those edges joins two walls.
    patch = bmesh.new()
    patch_rim = [patch.verts.new(v.co) for v in rim]
    ids = {v: i for i, v in enumerate(patch_rim)}
    base = patch.faces.new(patch_rim)
    patch.normal_update()
    cut = bmesh.ops.triangulate(patch, faces=[base], quad_method='BEAUTY', ngon_method='BEAUTY')
    triangles = [tuple(ids[v] for v in f.verts) for f in cut['faces']]
    patch.free()
    assert len(triangles) == len(rim) - 2
    centers = {}
    created = []
    bm.faces.remove(cap)
    for tri in triangles:
        contour = []
        for i, j in zip(tri, (*tri[1:], tri[0])):
            a, b = rim[i], rim[j]
            contour.append(a)
            if (i - j) % len(rim) not in (1, len(rim) - 1):
                key = tuple(sorted((i, j)))
                if key not in centers:
                    centers[key] = bm.verts.new((a.co + b.co) * .5 + Vector((0, -.0025, 0)))
                contour.append(centers[key])
        middle = sum((v.co for v in contour), Vector()) / len(contour) + Vector((0, -.001, 0))
        center = bm.verts.new(middle)
        for a, b in zip(contour, contour[1:] + contour[:1]):
            created.append(bm.faces.new((a, b, center)))
    return created


def num_components(bm):
    pending = set(bm.verts)
    count = 0
    while pending:
        count += 1
        search = [pending.pop()]
        while search:
            vertex = search.pop()
            for edge in vertex.link_edges:
                neighbor = edge.other_vert(vertex)
                if neighbor in pending:
                    pending.remove(neighbor)
                    search.append(neighbor)
    return count


def soften_roots(bm):
    # These are the small, irregular ends left by the cape-root split.
    # Outside the attachment zone, the original scan vertices stay untouched.
    lowest = min(v.co.z for v in bm.verts)
    weights = {}
    for vertex in bm.verts:
        p = vertex.co
        x = min(1., max(0., (abs(p.x) - .186) / .078))
        depth = min(1., max(0., (p.y - .211) / .044))
        weight = (1. - x*x * (3. - 2. * x)) * (1. - depth*depth * (3. - 2. * depth))
        if weight > 0.:
            weights[vertex] = weight
            p.y += weight * max(0., .219 - p.y)
            p.z += weight * max(0., lowest + .036 - p.z)

    for _ in range(3):
        updates = {}
        for vertex, weight in weights.items():
            if not vertex.is_boundary:
                continue
            neighbors = [e.other_vert(vertex) for e in vertex.link_edges if e.is_boundary]
            if len(neighbors) == 2:
                updates[vertex] = vertex.co.lerp((neighbors[0].co + neighbors[1].co) * .5, .34 * weight)
        for vertex, position in updates.items():
            vertex.co = position


def repair(wing):
    mesh = wing.data
    donors = fabric_donors(mesh)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    stitch_cut_edges(bm)
    soften_roots(bm)
    uv = bm.loops.layers.uv.active
    boundary = [edge for edge in bm.edges if edge.is_boundary]
    cap_faces = bmesh.ops.holes_fill(bm, edges=boundary, sides=0)['faces']
    for cap in cap_faces:
        center = cap.calc_center_median()
        donor = donors[1 if center.x > 0 else -1]
        for face in sew_cap(bm, cap):
            face.smooth = True
            for loop in face.loops:
                p = loop.vert.co - center
                loop[uv].uv = donor + Vector((.07 * p.x + .045 * p.y, .065 * p.z))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    assert all(edge.is_manifold and edge.is_contiguous for edge in bm.edges)
    assert num_components(bm) == 2
    assert len(bm.verts) - len(bm.edges) + len(bm.faces) == 4
    assert bm.calc_volume(signed=True) > 0
    report = {'boundaryEdgesBefore': len(boundary), 'boundaryEdgesAfter': 0, 'closedWingPairs': 2,
              'fabricDonors': {side: list(uv) for side, uv in donors.items()}}
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return report


def main():
    output = Path(sys.argv[-1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {pose: repair(bpy.data.objects['Wings • ' + pose]) for pose in ('Stand', 'Crouch')}
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'Boobees-original-wings-repaired.blend'))
    (output / 'repair.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
