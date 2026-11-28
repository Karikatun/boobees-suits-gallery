import json
from pathlib import Path

from mathutils import Matrix, Quaternion, Vector

HERE = Path(__file__).resolve().parent
SOURCE = json.loads((HERE/'semibot-native.json').read_text(encoding='utf-8'))


def transforms_for(pose):
    transforms, visible = [], []
    animation = SOURCE['poses'][pose]['transforms']
    for i, rest in enumerate(SOURCE['nodes']):
        node = rest | animation.get(str(i), {})
        p = node['parent']
        x,y,z,w = node['rot']
        tr = Matrix.LocRotScale(Vector(node['pos']), Quaternion((w,x,y,z)).normalized(), Vector(node['scale']))
        transforms.append(transforms[p] @ tr if p is not None else Matrix.Identity(4))
        visible.append(node['active'] and (p is None or visible[p]))
    return transforms, visible


def bounds(vertices):
    return [[round(fn(v[a] for v in vertices), 5) for a in range(3)] for fn in (min,max)]


def local(pose, anchor, names):
    transforms, active = transforms_for(pose)
    into = transforms[SOURCE['anchors'][anchor]].inverted_safe()
    result = []
    for mesh in SOURCE['meshes']:
        if active[mesh['node']] and mesh['name'] in names:
            tr = into @ transforms[mesh['node']]
            result.append((mesh['name'],[tr@Vector(v) for v in mesh['verts']],mesh['triangles']))
    return result


if __name__ == '__main__':
    result = {}
    kinds = {
        'Hood': ['player_head_top','player_head_bot_sphere','player_head_bot_flat','player_eye_L','player_eye_R'],
        'Bodice': ['player_body_top_sphere','player_body_top_flat','player_body_bot'],
        'Mantle': ['player_body_bot'],
        'Right Sleeve': ['player_arm_R'], 'Left Sleeve': ['player_arm_L'],
        'Right Sock': ['player_leg_R'], 'Left Sock': ['player_leg_L'],
    }
    for pose in SOURCE['poses']:
        ts, active = transforms_for(pose)
        report = {}
        for item, names in kinds.items():
            slot = SOURCE['anchors'][item]
            report[item] = {'anchorPosition':list(ts[slot].translation), 'anchorScale':list(ts[slot].to_scale()),
                            'anchorVisible':active[slot], 'meshes':{name:bounds(v) for name,v,_ in local(pose,item,names)}}
        result[pose] = report
    target = HERE/'fit-native-measures.json'
    target.write_text(json.dumps(result, indent=2),encoding='utf-8')
    for pose, recs in result.items():
        for name, r in recs.items():
            print(pose, name, r['anchorVisible'], [round(x,3) for x in r['anchorScale']], r['meshes'])
