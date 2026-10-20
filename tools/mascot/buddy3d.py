# KEYS BUDDY as a real 3D model (Blender, built from code) + motion test render.
#   /path/to/python-with-bpy buddy3d.py <out dir> [--still T] [--glb] [--res 720] [--samples 24]
# Timeline matches render2.py so the same soundtrack fits: walk 0-2.2s, jump 2.5-3.6s, 360 spin 4.0-5.2s, talk/wave 5.4-10s.
import math, os, sys
import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
OUT = args[0]
opt = lambda k, d=None: args[args.index(k) + 1] if k in args else d
STILL = opt('--still'); RES = int(opt('--res', 720)); SAMPLES = int(opt('--samples', 24))
FPS, SEC = 30, 10
WALK, JUMP, SPIN, TALK = (0.0, 2.2), (2.5, 3.6), (4.0, 5.2), 5.4

def hexrgb(h, a=1.0):
    h = h.lstrip('#'); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c) + (a,)

BLUE, BLUE2, NAVY, NAVY2, CREAM, BG = '#0641FF', '#013EC7', '#0B1C4F', '#14286a', '#E9E4DA', '#EEF1F8'

# ---------------- scene
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.device = 'CPU'; sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
sc.cycles.max_bounces = 6
sc.render.resolution_x, sc.render.resolution_y = RES, RES * 16 // 9
sc.render.fps = FPS; sc.frame_start, sc.frame_end = 1, FPS * SEC
sc.view_settings.view_transform = 'Standard'; sc.render.film_transparent = True
sc.render.image_settings.file_format = 'PNG'

def mat(name, color, rough=0.5, sss=0.0, coat=0.0, emit=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = hexrgb(color)
    b.inputs['Roughness'].default_value = rough
    if sss:
        b.inputs['Subsurface Weight'].default_value = sss
        b.inputs['Subsurface Radius'].default_value = (0.08, 0.08, 0.12)
        b.inputs['Subsurface Scale'].default_value = 0.05
    if coat: b.inputs['Coat Weight'].default_value = coat; b.inputs['Coat Roughness'].default_value = 0.35
    if emit:
        b.inputs['Emission Color'].default_value = hexrgb(color); b.inputs['Emission Strength'].default_value = emit
    return m

M = dict(blue=mat('blue', BLUE, 0.42, 0.15, 0.25), blue2=mat('blue2', BLUE2, 0.45, 0.15, 0.2),
         navy=mat('navy', NAVY, 0.55, 0.12, 0.1), navy2=mat('navy2', NAVY2, 0.55, 0.12, 0.1),
         cream=mat('cream', CREAM, 0.5, 0.2), eye=mat('eye', '#FFF8EA', 0.3, 0.0, 0.0, 0.6),
         floor=mat('floor', BG, 0.9))

world = bpy.data.worlds.new('w'); sc.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = hexrgb(BG)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.35

def smooth_obj(o, level=2):
    o.modifiers.new('sub', 'SUBSURF').levels = level
    o.modifiers['sub'].render_levels = level
    for p in o.data.polygons: p.use_smooth = True

def blob(name, mat_, loc, scale, rot=(0, 0, 0), parent=None, level=2):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=loc, rotation=rot)
    o = bpy.context.object; o.name = name; o.scale = scale
    o.data.materials.append(M[mat_]); smooth_obj(o, 1)
    if parent: keep_parent(o, parent)
    return o

def capsule(name, mat_, a, b, r, parent=None):
    """rounded rod from a to b (world coords at build time)"""
    a, b = Vector(a), Vector(b); d = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=r, depth=d.length, location=(a + b) / 2)
    o = bpy.context.object; o.name = name
    o.rotation_mode = 'QUATERNION'; o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d)
    o.data.materials.append(M[mat_])
    for p in o.data.polygons: p.use_smooth = True
    caps = [blob(name + '_ca', mat_, a, (r, r, r)), blob(name + '_cb', mat_, b, (r, r, r))]
    if parent:
        keep_parent(o, parent)
        for c in caps: keep_parent(c, parent)
    return o

def curve(name, mat_, pts, bevel, parent=None, closed=False, fill=False, extrude=0.0):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '2D' if fill else '3D'
    sp = cu.splines.new('BEZIER'); sp.bezier_points.add(len(pts) - 1); sp.use_cyclic_u = closed
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = p; bp.handle_left_type = bp.handle_right_type = 'AUTO'
    cu.bevel_depth = bevel; cu.bevel_resolution = 6; cu.extrude = extrude
    if fill: cu.fill_mode = 'BOTH'
    o = bpy.data.objects.new(name, cu); sc.collection.objects.link(o); o.data.materials.append(M[mat_])
    if parent: keep_parent(o, parent)
    return o

def empty(name, loc, parent=None):
    o = bpy.data.objects.new(name, None); o.location = loc; sc.collection.objects.link(o)
    if parent: o.parent = parent; o.location = Vector(loc) - parent.matrix_world.translation
    bpy.context.view_layer.update()
    return o

def keep_parent(o, p):
    bpy.context.view_layer.update()
    mw = o.matrix_world.copy(); o.parent = p; o.matrix_parent_inverse = p.matrix_world.inverted(); o.matrix_world = mw

# ---------------- character (faces -Y, feet on z=0, about 3.5 units tall)
root = empty('root', (0, 0, 0))
hips = empty('hips', (0, 0, 0.78), root)
chest = empty('chest', (0, 0, 0.95), hips)
blob('torso', 'navy', (0, 0, 1.22), (0.66, 0.52, 0.66), parent=chest)
blob('belly', 'navy', (0, 0.06, 0.92), (0.58, 0.44, 0.4), parent=chest)
# bib: cream V-shaped patch = torso shell intersected with a V prism in front of the chest
import bmesh
def prism(name, pts_xz, y0, y1):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    f0 = [bm.verts.new((x, y0, z)) for x, z in pts_xz]; f1 = [bm.verts.new((x, y1, z)) for x, z in pts_xz]
    bm.faces.new(f0); bm.faces.new(list(reversed(f1)))
    n = len(pts_xz)
    for i in range(n): bm.faces.new((f0[i], f0[(i + 1) % n], f1[(i + 1) % n], f1[i]))
    bm.normal_update(); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); sc.collection.objects.link(o); o.hide_render = True; o.hide_set(True)
    return o
vcut = prism('bibcut', [(-0.46, 1.66), (-0.2, 1.56), (0.0, 1.42), (0.2, 1.56), (0.46, 1.66), (0.34, 1.12), (0.16, 0.78),
                        (0.0, 0.66), (-0.16, 0.78), (-0.34, 1.12)], -1.2, -0.1)
bib = blob('bib', 'cream', (0, 0, 1.22), (0.66 * 1.03, 0.52 * 1.04, 0.66 * 1.03))
bib.modifiers.remove(bib.modifiers['sub'])
bo = bib.modifiers.new('cut', 'BOOLEAN'); bo.operation = 'INTERSECT'; bo.object = vcut; bo.solver = 'EXACT'
bib.modifiers.new('thick', 'SOLIDIFY').thickness = 0.02
keep_parent(bib, chest); keep_parent(vcut, chest)
# keys logo on the bib: three short strokes like the brand mark
for i, (a, b) in enumerate([((-0.02, -0.56, 1.30), (0.1, -0.555, 1.42)), ((-0.06, -0.57, 1.24), (0.1, -0.56, 1.12)),
                             ((-0.0, -0.565, 1.14), (0.08, -0.555, 1.05))]):
    curve(f'logo{i}', 'blue' if i < 2 else 'navy', [a, b], 0.028, parent=chest)

neck = empty('neck', (0, 0, 1.78), chest)
head = empty('head', (0, 0, 1.9), neck)
blob('skull', 'navy', (0, 0.02, 2.32), (0.92, 0.82, 0.78), parent=head)
blob('cheekwrap', 'navy2', (-0.2, -0.16, 2.1), (0.86, 0.72, 0.2), rot=(0.22, 0.16, -0.12), parent=head)
blob('hatband', 'blue2', (0.08, 0.04, 2.86), (1.02, 0.86, 0.3), rot=(0.05, -0.12, 0.05), parent=head)
blob('hatband_top', 'blue', (0.1, 0.03, 2.98), (0.92, 0.78, 0.22), rot=(0.05, -0.12, 0.05), parent=head)
blob('hattop', 'blue', (0.02, 0.0, 3.36), (0.86, 0.46, 0.2), rot=(0, -0.42, 0.08), parent=head)
blob('hattop_tip', 'blue', (0.62, 0.0, 3.62), (0.3, 0.36, 0.19), rot=(0, -0.6, 0.08), parent=head)
blob('eyeL', 'eye', (-0.27, -0.76, 2.42), (0.085, 0.05, 0.13), parent=head)
blob('eyeR', 'eye', (0.27, -0.76, 2.42), (0.085, 0.05, 0.13), parent=head)
mouth = curve('mouth', 'eye', [(-0.13, -0.79, 2.22), (0.0, -0.81, 2.16), (0.13, -0.79, 2.22)], 0.022, parent=head)
bpy.ops.object.select_all(action='DESELECT'); mouth.select_set(True); bpy.context.view_layer.objects.active = mouth
bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')  # scale the mouth around itself, not around the floor

def arm(side):
    s = 1 if side == 'R' else -1
    sh = empty('shoulder' + side, (0.56 * s, 0, 1.5), chest)
    capsule('arm' + side, 'navy', (0.56 * s, 0, 1.5), (0.78 * s, -0.02, 0.98), 0.15, parent=sh)
    hand = empty('hand' + side, (0.8 * s, -0.03, 0.92), sh)
    blob('palm' + side, 'navy', (0.82 * s, -0.04, 0.86), (0.2, 0.15, 0.2), parent=hand)
    blob('thumb' + side, 'navy', (0.76 * s, -0.14, 0.9), (0.06, 0.06, 0.09), rot=(0.3, 0, 0), parent=hand)
    return sh, hand

def leg(side):
    s = 1 if side == 'R' else -1
    hp = empty('hip' + side, (0.27 * s, 0, 0.78), hips)
    capsule('leg' + side, 'navy', (0.27 * s, 0, 0.72), (0.29 * s, 0, 0.24), 0.2, parent=hp)
    blob('foot' + side, 'navy', (0.3 * s, -0.12, 0.13), (0.27, 0.36, 0.15), parent=hp)
    return hp

shL, handL = arm('L'); shR, handR = arm('R')
hipL, hipR = leg('L'), leg('R')

# floor + lights + camera
bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0)); fl = bpy.context.object; fl.data.materials.append(M['floor']); fl.is_shadow_catcher = True
def light(name, loc, energy, size, color='#FFFFFF'):
    d = bpy.data.lights.new(name, 'AREA'); d.energy = energy; d.size = size; d.color = hexrgb(color)[:3]
    o = bpy.data.objects.new(name, d); o.location = loc; sc.collection.objects.link(o)
    c = o.constraints.new('TRACK_TO'); c.target = hips; c.track_axis = 'TRACK_NEGATIVE_Z'; c.up_axis = 'UP_Y'
    return o
light('key', (-2, -6, 10), 1000, 9)
light('fill', (6, -5, 3), 300, 6, '#DDE6FF')
light('rim', (2, 6, 6), 900, 3, '#BFD0FF').data.use_shadow = False
cam_d = bpy.data.cameras.new('cam'); cam_d.lens = 50; cam_d.sensor_fit = 'VERTICAL'; cam_d.sensor_height = 36
cam = bpy.data.objects.new('cam', cam_d); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, -11.5, 2.4)
tgt = empty('camtarget', (0, 0, 2.15)); c = cam.constraints.new('TRACK_TO'); c.target = tgt
c.track_axis = 'TRACK_NEGATIVE_Z'; c.up_axis = 'UP_Y'

# ---------------- animation
def sm(t): t = min(max(t, 0), 1); return t * t * (3 - 2 * t)
for o in (root, hips, chest, neck, head, shL, shR, handL, handR, hipL, hipR, mouth):
    o.rotation_mode = 'XYZ'
BASE = {o.name: (o.location.copy(), o.scale.copy()) for o in (root, hips, chest, head, mouth)}
mouth_rest = mouth.scale.copy()

def pose(t):
    x, z, yaw, sx, sz = 0.0, 0.0, 0.0, 1.0, 1.0
    bob, lean, roll = 0.0, 0.0, 0.0
    legL = legR = armL = armR = 0.0      # swing about X (forward/back)
    armL_out, armR_out = 0.12, 0.12       # raise sideways about Y
    elbowR = 0.0; head_tilt = 0.0; head_turn = 0.0; mouth_open = 0.0
    if t < WALK[1]:
        k = sm(t / WALK[1]); x = -5.2 + 5.2 * k
        yaw = math.radians(90) * (1 - sm((t - 1.6) / 0.6))           # walks sideways, turns to camera at the end
        ph = t * 2.8 * 2 * math.pi * (1 - 0.6 * sm((t - 1.7) / 0.5))
        amp = 1 - sm((t - 1.8) / 0.4)
        legL, legR = 0.55 * math.sin(ph) * amp, -0.55 * math.sin(ph) * amp
        armL, armR = -0.5 * math.sin(ph) * amp, 0.5 * math.sin(ph) * amp
        bob = abs(math.cos(ph)) * 0.09 * amp; roll = 0.06 * math.sin(ph) * amp; lean = 0.08 * amp
    elif t < JUMP[0]:
        q = (t - WALK[1]) / (JUMP[0] - WALK[1]); head_tilt = 0.08 * math.sin(q * math.pi)
    elif t < JUMP[1]:
        q = t - JUMP[0]; d = JUMP[1] - JUMP[0]
        if q < 0.2:
            a = sm(q / 0.2); sz, sx = 1 - 0.16 * a, 1 + 0.1 * a
            armL = armR = 0.4 * a; legL = legR = 0
        elif q < d - 0.25:
            a = (q - 0.2) / (d - 0.45); z = math.sin(a * math.pi) * 0.95
            st = 0.12 * (1 - abs(2 * a - 1)); sz, sx = 1 + st, 1 - st * 0.5
            armL_out = armR_out = 0.12 + 1.6 * math.sin(a * math.pi)
            legL, legR = 0.35 * math.sin(a * math.pi), -0.15 * math.sin(a * math.pi)
        else:
            a = (q - (d - 0.25)) / 0.25; sq = 0.18 * math.sin(a * math.pi) * (1 - a * 0.4); sz, sx = 1 - sq, 1 + sq * 0.6
    elif t < SPIN[1] + 0.25:
        q = (t - SPIN[0]) / (SPIN[1] - SPIN[0]) if t >= SPIN[0] else 0
        yaw = sm(q) * 2 * math.pi; z = math.sin(min(q, 1) * math.pi) * 0.35
        armL_out = armR_out = 0.12 + 1.1 * math.sin(min(q, 1) * math.pi)
        roll = 0.05 * math.sin(min(q, 1) * math.pi * 2)
    else:
        u = t - TALK
        bob = 0.025 * math.sin(u * 2 * math.pi * 0.8)
        head_tilt = 0.07 * math.sin(u * 2 * math.pi * 0.4); head_turn = 0.12 * math.sin(u * 2 * math.pi * 0.25)
        if u < 1.8:      # wave hello with the right hand
            w = sm(u / 0.3) * (1 - sm((u - 1.5) / 0.3))
            armR_out = 0.12 + 1.85 * w; armR = -0.55 * w; elbowR = 0.5 * math.sin(u * 2 * math.pi * 2.2) * w
        elif u < 3.4:    # open palm towards the side, like the presenter pose
            w = sm((u - 1.8) / 0.3) * (1 - sm((u - 3.1) / 0.3)); armR_out = 0.12 + 0.9 * w; armR = -0.6 * w
        else:            # hand on hip + nod
            w = sm((u - 3.4) / 0.3); armL_out = 0.12 + 0.35 * w; head_tilt += 0.08 * math.sin((u - 3.4) * 7) * w
        mouth_open = max(0.0, math.sin(u * 2 * math.pi * 3.3)) * (0.6 + 0.4 * math.sin(u * 5.1)) if u < 4.4 else 0
    return locals()

def apply(t):
    p = pose(t)
    root.location = (p['x'], 0, p['z']); root.rotation_euler = (0, 0, p['yaw']); root.scale = (p['sx'], p['sx'], p['sz'])
    hips.location = BASE['hips'][0] + Vector((0, 0, p['bob'])); hips.rotation_euler = (p['lean'], p['roll'], 0)
    head.rotation_euler = (p['head_tilt'] * 0.4, p['head_tilt'], p['head_turn'])
    hipL.rotation_euler = (p['legL'], 0, 0); hipR.rotation_euler = (p['legR'], 0, 0)
    shL.rotation_euler = (p['armL'], p['armL_out'], 0); shR.rotation_euler = (p['armR'], -p['armR_out'], 0)
    handR.rotation_euler = (0, p['elbowR'], 0)
    mouth.scale = (mouth_rest.x * (1 - 0.15 * p['mouth_open']), mouth_rest.y, mouth_rest.z * (1 + 2.2 * p['mouth_open']))

animated = (root, hips, head, hipL, hipR, shL, shR, handR, mouth)
for f in range(sc.frame_start, sc.frame_end + 1):
    apply((f - 1) / FPS)
    for o in animated:
        o.keyframe_insert('location', frame=f); o.keyframe_insert('rotation_euler', frame=f); o.keyframe_insert('scale', frame=f)

os.makedirs(OUT, exist_ok=True)
if '--glb' in args:
    fl.hide_set(True); fl.hide_render = True
    bpy.ops.object.select_all(action='DESELECT')
    for o in sc.objects:
        if o.type in ('MESH', 'CURVE', 'EMPTY') and o is not fl and o.name != 'camtarget': o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, 'buddy.glb'), use_selection=True, export_apply=True,
                              export_animations=True, export_animation_mode='SCENE', export_frame_range=True, export_force_sampling=True, export_yup=True)
    print('glb written'); sys.exit(0)
if STILL is not None:
    sc.frame_set(int(float(STILL) * FPS) + 1); sc.render.filepath = os.path.join(OUT, f'still_{STILL}.png')
    bpy.ops.render.render(write_still=True); print('still', sc.render.filepath); sys.exit(0)
fs, fe = int(opt('--from', sc.frame_start)), int(opt('--to', sc.frame_end))
for f in range(fs, fe + 1):
    sc.frame_set(f); sc.render.filepath = os.path.join(OUT, f'f{f:04d}.png'); bpy.ops.render.render(write_still=True)
print('frames done')
