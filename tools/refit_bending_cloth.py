"""Extend overlapping fabric at the jaw and waist while retaining the source cloth and UVs."""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_semibot_outfit import poses, smooth


def fit_bodice(mesh):
    top = max(v.co.z for v in mesh.vertices)
    for vertex in mesh.vertices:
        p = vertex.co
        neck = smooth(top - .105, top, p.z)
        p.x *= 1 - .059 * neck
        p.y *= 1 - .036 * neck
        p.z -= .009 * neck
    mesh.update()


def fit_lower_hood(mesh):
    for vertex in mesh.vertices:
        p = vertex.co
        round_edge = 1 - smooth(-.111, -.016, p.z)
        # Pull the lowest folds into a round dome under the jaw, with an overlap into the bodice.
        p.z -= .094 * round_edge
        radius = 1 - .19 * round_edge * round_edge
        p.x *= radius
        p.y *= radius
    mesh.update()


def fit_hem(mesh, pose):
    top = max(v.co.z for v in mesh.vertices)
    extension = .081 if pose == 'Stand' else .055
    for vertex in mesh.vertices:
        p = vertex.co
        underlap = smooth(top - .081, top, p.z)
        p.z += extension * underlap
        p.x *= 1 - .027 * underlap
        p.y *= 1 - .027 * underlap
    mesh.update()


def main():
    output = Path(sys.argv[-1]).resolve()
    for pose in poses:
        fit_bodice(bpy.data.objects['Bodice • ' + pose].data)
        fit_lower_hood(bpy.data.objects['Hood Lower • ' + pose].data)
        fit_hem(bpy.data.objects['Hem • ' + pose].data, pose)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output))


if __name__ == '__main__':
    main()
