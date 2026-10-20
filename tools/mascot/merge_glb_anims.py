# python3 merge_glb_anims.py file.glb  — merge every glTF animation into one clip named "motion" (model-viewer plays one at a time)
import json, struct, sys

p = sys.argv[1]
b = open(p, 'rb').read()
jl = struct.unpack('<I', b[12:16])[0]
j = json.loads(b[20:20 + jl]); rest = b[20 + jl:]
anims = j.get('animations', [])
if len(anims) > 1:
    out = {'name': 'motion', 'channels': [], 'samplers': []}
    for a in anims:
        off = len(out['samplers'])
        out['samplers'] += a['samplers']
        out['channels'] += [{**c, 'sampler': c['sampler'] + off} for c in a['channels']]
    j['animations'] = [out]
js = json.dumps(j, separators=(',', ':')).encode()
js += b' ' * (-len(js) % 4)
body = struct.pack('<II', len(js), 0x4E4F534A) + js + rest
open(p, 'wb').write(b[:8] + struct.pack('<I', 12 + len(body)) + body)
print('animations:', len(j['animations']), 'channels:', len(j['animations'][0]['channels']))
