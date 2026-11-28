#!/usr/bin/env python3
"""Generate a project-authored skinned primitive and freeze its complete rig report.

No external asset or prior report is read. This fixture has real joint/weight
attributes, true inverse translations and three authored animation channels.
The freeze is canonical JSON comparison evidence for this synthetic input only.
"""
import hashlib
import json
import io
from pathlib import Path
import struct
import sys
from contextlib import redirect_stdout
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tests/fixtures/oracle-synthetic'
JOINT_ORDER = [5, 2, 6, 1, 4, 3]


def generate_glb():
    binary = bytearray()
    views, accessors = [], []

    def add(values, kind, components, component=5126, **metadata):
        while len(binary) % 4:
            binary.append(0)
        offset = len(binary)
        binary.extend(struct.pack('<' + ('f' if component == 5126 else 'H') * len(values), *values))
        views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(binary)-offset})
        accessors.append({'bufferView': len(views)-1, 'componentType': component,
                          'count': len(values)//components, 'type': kind, **metadata})
        return len(accessors)-1

    # Three disjoint triangles; all vertices are genuinely skinned. At each
    # height the centre chain and one branch share mass, never an unbound vertex.
    positions = [-.2,0,0,.2,0,0,0,.4,0, -.2,1,0,.2,1,0,0,1.4,0, -.2,2,0,.2,2,0,0,3,0]
    position = add(positions,'VEC3',3,min=[-.2,0,0],max=[.2,3,0])
    normals = add([0,0,1]*9,'VEC3',3)
    skin_indices = []
    for node in [1,1,1,2,2,2,5,5,6]:
        skin_indices.extend([JOINT_ORDER.index(node),JOINT_ORDER.index(3),0,0])
    joints = add(skin_indices,'VEC4',4,5123)
    weights = add([.75,.25,0,0]*9,'VEC4',4)
    world = {1:[0,0,0],2:[0,1,0],3:[-1,1,0],4:[1,1,0],5:[0,2,0],6:[0,3,0]}
    inverse = []
    for node in JOINT_ORDER:
        x,y,z = world[node]
        inverse.extend([1,0,0,0,0,1,0,0,0,0,1,0,-x,-y,-z,1])
    binds = add(inverse,'MAT4',16)
    times = add([0,.5,1],'SCALAR',1,min=[0],max=[1])
    translation = add([0,0,0,.25,0,0,0,0,0],'VEC3',3)
    rotation = add([0,0,0,1,0,0,.6,.8,0,0,0,1],'VEC4',4)
    scale = add([1,1,1,1.2,1,1,1,1,1],'VEC3',3)
    animations = []
    for name,node,path,values in [('slide',1,'translation',translation),('turn',3,'rotation',rotation),('stretch',4,'scale',scale)]:
        animations.append({'name':name,'samplers':[{'input':times,'output':values,'interpolation':'LINEAR'}],
                           'channels':[{'sampler':0,'target':{'node':node,'path':path}}]})
    document = {
        'asset':{'version':'2.0','generator':'project-authored synthetic rig oracle'},
        'scene':0,'scenes':[{'nodes':[0]}],
        'nodes':[{'name':'PrimitiveRoot','children':[1,7]},
                 {'name':'JointA','children':[2,3,4]},
                 {'name':'JointB','translation':[0,1,0],'children':[5]},
                 {'name':'JointC','translation':[-1,1,0]},
                 {'name':'JointD','translation':[1,1,0]},
                 {'name':'JointE','translation':[0,1,0],'children':[6]},
                 {'name':'JointF','translation':[0,1,0]},
                 {'name':'PrimitiveTriangles','mesh':0,'skin':0}],
        'meshes':[{'name':'PrimitiveTriangles','primitives':[{'attributes':{'POSITION':position,'NORMAL':normals,'JOINTS_0':joints,'WEIGHTS_0':weights}}]}],
        'skins':[{'name':'PrimitiveSkin','skeleton':1,'joints':JOINT_ORDER,'inverseBindMatrices':binds}],
        'animations':animations,'buffers':[{'byteLength':len(binary)}],'bufferViews':views,'accessors':accessors}
    encoded = json.dumps(document,separators=(',',':')).encode()
    encoded += b' ' * (-len(encoded)%4)
    binary += b'\0' * (-len(binary)%4)
    body = struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(binary),0x004e4942)+binary
    return struct.pack('<4sII',b'glTF',2,len(body)+12)+body


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    asset = OUT / 'synthetic-rig.glb'
    asset.write_bytes(generate_glb())
    # Use the actual reporter without workspace persistence. The standalone CLI's
    # workspace admission requires an installed core; fixture generation does not.
    sys.path.insert(0, str(ROOT / 'tools'))
    import rig_glb_reference
    captured = io.StringIO()
    with redirect_stdout(captured):
        code = rig_glb_reference.main([str(asset)])
    if code:
        raise RuntimeError(captured.getvalue())
    report = json.loads(captured.getvalue())
    report['path'] = 'synthetic-rig.glb'  # sole volatile field in the oracle comparator
    (OUT/'glb-rig.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    entries = []
    for path in (asset,OUT/'glb-rig.json'):
        data=path.read_bytes();entries.append({'path':path.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    (OUT/'manifest.json').write_text(json.dumps({'scope':'Independently authored synthetic rig, not third-party or native fidelity evidence.',
                                               'generator':'tools/generate_synthetic_rig_oracle.py','files':entries},indent=2)+'\n')


if __name__ == '__main__':
    main()
